#!/usr/bin/env python
'''
get_med_metfcst.py
usage: <python> <get_med_metfcst.py> <configuration.cfg>
This script downloads downscaled CFSv2 90-day meteorological forecast
data from
https://tds-proxy.nkn.uidaho.edu/thredds/fileServer/
    NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/bcsd-nmme/cfsv2_metdata_90day/
delivered through OPeNDAP. Because attributes are lost during download,
they are added back in. To start, we just download multi-model ensemble mean.
'''
import os
import argparse
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import xarray as xr
from cdo import Cdo
import cf_units

from tonic.io import read_config
from monitor import model_tools


def main():
    ''' Download meteorological forecast data for 90-day forecast
        from http://thredds.northwestknowledge.net:8080/thredds/catalog/
        NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/cfsv2_metdata_90day/catalog.html
    '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Download met forecast data')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)

    # initialize cdo
    cdo = Cdo()

    # read in meteorological data location
    met_fcst_loc = config_dict['MED_FCST']['Met_Loc']
    old_config_file = config_dict['ECFLOW']['old_Config']
    new_config_file = config_dict['ECFLOW']['new_Config']

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # define variable names used when filling threads URL
    # an abbreviation and a full name is needed
    varnames = {'vs': 'wind_speed', 'tmmx': 'air_temperature',
                'tmmn': 'air_temperature',
                'srad': 'surface_downwelling_shortwave_flux_in_air',
                'sph': 'specific_humidity', 'pr': 'precipitation_amount',
                'pet': 'potential_evapotranspiration'}
    # define model names for file name
    modelnames = ['CFSv2']
    # ['NCAR', 'NASA', 'GFDL', 'GFDL-FLOR', 'ENSMEAN', 'CMC1', 'CMC2',
    #              'CFSv2']
    new_units = {'vs': 'm s-1', 'sph': 'kg kg-1',
                 'tmmx': 'degC', 'tmmn': 'degC', 'srad': 'W m-2',
                 'pr': 'mm', 'pet': 'mm'}

    # download metdata from http://thredds.northwestknowledge.net
    for model in modelnames:
        dlist = []
        for var, name in varnames.items():
            url = ('http://thredds.northwestknowledge.net:8080/thredds/dodsC/' +
                   'NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/' +
                   'cfsv2_metdata_90day/' +
                   'cfsv2_metdata_forecast_%s_daily.nc' % (var))
            print('Reading {0}'.format(url))
            xds = xr.open_dataset(url)
            if name == 'air_temperature':
                # Change variable names so that tmmn and tmax are different
                xds.rename({'air_temperature': var}, inplace=True)
            dlist.append(xds)
        merge_ds = xr.merge(dlist)
        # MetSim requires time dimension be named "time"
        merge_ds.rename({'day': 'time'}, inplace=True)
        for var in ('tmmn', 'tmmx'):
            units_in = cf_units.Unit(merge_ds[var].attrs['units'])
            units_out = cf_units.Unit(new_units[var])
            # Perform units conversion
            units_in.convert(merge_ds[var].values[:], units_out, inplace=True)
            # Fix _FillValue after unit conversion
            merge_ds[var].values[merge_ds[var].values < -30000] = -32767.
            merge_ds[var].attrs['units'] = new_units[var]
        # MetSim requires time dimension be named "time"
        merge_ds = merge_ds.transpose('time', 'lat', 'lon')
        # Make sure tmax >= tmin always
        tmin = np.copy(merge_ds['tmmn'].values)
        tmax = np.copy(merge_ds['tmmx'].values)
        swap_values = ((tmin > tmax) & (tmax != -32767.))
        merge_ds['tmmn'].values[swap_values] = tmax[swap_values]
        merge_ds['tmmx'].values[swap_values] = tmin[swap_values]
        end_date = pd.to_datetime(merge_ds['time'].values[-1])
        start_date = datetime.strptime(config_dict['MONITOR']['End_Date'],
                                       '%Y-%m-%d') + timedelta(days=1)
        start_date_format = start_date.strftime('%Y-%m-%d')
        end_date_format = end_date.strftime('%Y-%m-%d')
        vic_save_state_format = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
        # replace start date, end date and met location in the configuration
        # file. SEAS_* variables will be defined in get_seasonal_metfcst.py.
        # replace those keywords with dummy variable (-9999) so that
        # replace_var_pythonic_config() won't fail.
        kwargs = {'START_DATE': config_dict['MONITOR']['Start_Date'],
                  'END_DATE': config_dict['MONITOR']['End_Date'],
                  'VIC_SAVE_STATE': config_dict['MONITOR']['vic_save_state'],
                  'MED_START_DATE': start_date_format,
                  'MED_END_DATE': end_date_format,
                  'MED_VIC_SAVE_STATE': vic_save_state_format,
                  'SEAS_START_DATE': -9999,
                  'SEAS_END_DATE': -9999,
                  'SEAS_VIC_SAVE_STATE':-9999}
        model_tools.replace_var_pythonic_config(old_config_file,
                                                new_config_file,
                                                header=None, **kwargs)

        outfile = os.path.join(met_fcst_loc, '%s.nc' % (model))
        print('Conservatively remap and write to {0}'.format(outfile))
        # write merge_ds to a temporary file so that we don't run into
        # issues with the system /tmp directoy filling up
        temporary = os.path.join(config_dict['ECFLOW']['TempDir'],
                                 'med_temp_{}'.format(model))
        merge_ds.to_netcdf(temporary)
        cdo.remapcon(grid_file, input=temporary, output=outfile)
        os.remove(temporary)


if __name__ == "__main__":
    main()

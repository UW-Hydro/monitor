#!/usr/bin/env python
'''
get_seasonal_metfcst.py
usage: <python> <get_seasonal_metfcst.py> <configuration.cfg>
This script downloads downscaled NMME meteorological forecast data through
xarray from
http://proxy.nkn.uidaho.edu/thredds/catalog/
    NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/bcsd-nmme/dailyForecasts/
    catalog.html
delivered through OPeNDAP. Because attributes are lost during download,
they are added back in. To start, we just download multi-model ensemble mean.
'''
import os
import argparse
from datetime import datetime, timedelta
import pandas as pd
import xarray as xr
from cdo import Cdo
import cf_units

from tonic.io import read_config
from monitor import model_tools


def read_and_convert_data(model, var):
    ''' Read data from URL for model and var, then convert variable units
        to metric '''
    url = ('http://tds-proxy.nkn.uidaho.edu/thredds/dodsC/' +
           'NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/bcsd-nmme/' +
           'dailyForecasts/' +
           'bcsd_nmme_metdata_%s_forecast_%s_daily.nc' % (
               model, var))
    print('Reading {0}'.format(url))
    xds = xr.open_dataset(url)
    # Define units
    if xds[var].attrs['units'] == 'F':
        xds[var].attrs['units'] = 'degF'
    new_units = {'was': 'm s-1', 'dps': 'degC', 'tasmean': 'degC',
                 'tasmax': 'degC', 'tasmin': 'degC', 'rsds': 'W m-2',
                 'pr': 'mm', 'pet': 'mm'}
    units_in = cf_units.Unit(xds[var].attrs['units'])
    units_out = cf_units.Unit(new_units[var])
    # Perform units conversion
    units_in.convert(xds[var].values[:], units_out, inplace=True)
    xds[var].attrs['units'] = new_units[var]
    return xds


def get_dates(config_dict, merge_ds):
    ''' Define dates to use in updated configuration file. Start comes from
        the last day of the medium range forecast, and end is taken from the
        downloaded data. '''
    end_date = pd.to_datetime(merge_ds.time.values[-1])
    start_date = datetime.strptime(config_dict['MED_FCST']['End_Date'],
                                   '%Y-%m-%d') + timedelta(days=1)
    start_date_format = start_date.strftime('%Y-%m-%d')
    end_date_format = end_date.strftime('%Y-%m-%d')
    vic_save_state_format = (end_date + timedelta(days=1)).strftime(
        '%Y-%m-%d')
    # replace start date, end date and met location in the configuration
    # file
    return {'START_DATE': config_dict['MONITOR']['Start_Date'],
            'END_DATE': config_dict['MONITOR']['End_Date'],
            'VIC_SAVE_STATE': config_dict['MONITOR']['vic_save_state'],
            'MED_START_DATE': config_dict['MED_FCST']['Start_Date'],
            'MED_END_DATE': config_dict['MED_FCST']['End_Date'],
            'MED_VIC_SAVE_STATE':
            config_dict['MED_FCST']['vic_save_state'],
            'SEAS_START_DATE': start_date_format,
            'SEAS_END_DATE': end_date_format,
            'SEAS_VIC_SAVE_STATE': vic_save_state_format}


def main():
    ''' Download seasonal meteorological forecasts from
        http://proxy.nkn.uidaho.edu/thredds/catalog/
        NWCSC_INTEGRATED_SCENARIOS_ALL_CLIMATE/bcsd-nmme/dailyForecasts/
        catalog.html and reformat for use in MetSim '''

    parser = argparse.ArgumentParser(description='Download met forecast data')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)

    # initialize cdo
    cdo = Cdo()

    # read in meteorological data location
    met_fcst_loc = config_dict['SEAS_FCST']['Met_Loc']

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # define variable names used when filling threads URL
    # an abbreviation and a full name is needed
    varnames = ['was', 'dps', 'tasmean', 'tasmax', 'tasmin', 'rsds',
                'pr', 'pet']
    # define model names for file name
    modelnames = ['ENSMEAN']
    # ENSMEAN is used for initial testing/workflow. Eventually, we'll
    # want to add the rest in. The available ensemble members are:
    # ['NCAR', 'NASA', 'GFDL', 'GFDL-FLOR', 'ENSMEAN', 'CMC1', 'CMC2',
    #              'CFSv2']
    # download metdata from http://thredds.northwestknowledge.net
    for model in modelnames:
        dlist = []
        for var in varnames:
            dlist.append(read_and_convert_data(model, var))
        merge_ds = xr.merge(dlist)
        merge_ds = merge_ds.transpose('time', 'lat', 'lon')
        kwargs = get_dates(config_dict, merge_ds)
        # replace start date, end date and met location in the configuration
        # file
        model_tools.replace_var_pythonic_config(
            config_dict['ECFLOW']['old_Config'],
            config_dict['ECFLOW']['new_Config'], header=None, **kwargs)
        outfile = os.path.join(met_fcst_loc, '%s.nc' % (model))
        print('Conservatively remap and write to {0}'.format(outfile))
        # write merge_ds to a temporary file so that we don't run into
        # issues with the system /tmp directoy filling up
        temporary = os.path.join(config_dict['ECFLOW']['TempDir'],
                                 'seasonal_fcst_temp.nc')
        merge_ds.to_netcdf(temporary)
        cdo.remapcon(grid_file, input=temporary, output=outfile)
        os.remove(temporary)


if __name__ == '__main__':
    main()

#!/usr/bin/env python
'''
get_metdata_range.py
usage: <python> <get_metdata_range.py> <configuration.cfg> <start_date>
       <end_date>
This script downloads meteorological data through xarray from
http://thredds.northwestknowledge.net:8080/thredds/
  reacch_climate_MET_catalog.html
delivered through OPeNDAP. Dates are read from command line in YYYY-MM-DD
format.
'''
import argparse
import calendar
from datetime import datetime, timedelta
import cf_units
from cdo import Cdo
import xarray as xr
import numpy as np
import os

from tonic.io import read_config
from monitor import model_tools


def define_url(var, year, num_lon, num_lat, num_day):
    ''' create url for Northwest Knowlegdge Network gridMet download '''
    return ('http://thredds.northwestknowledge.net:8080/thredds/dodsC/MET/' +
            '{0}/{0}_{1}.nc?lon[0:1:{2}],lat[0:1:{3}],day[{4}:1:{5}],'.format(
                var[0], year, num_lon, num_lat, num_day[0], num_day[1]) +
            '{0}[{1}:1:{2}][0:1:{3}][0:1:{4}]'.format(
                var[1], num_day[0], num_day[1], num_lon, num_lat))


def main():
    '''
    Download data from
    http://thredds.northwestknowledge.net:8080/thredds/
      reacch_climate_MET_catalog.html
    delivered through OPeNDAP. Because attributes are lost during download,
    they are added back in.
    '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Download met data')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file, used for file and ' +
                             'directory locations. dates taken from ' +
                             'command line arguments for MONITOR ' +
                             'and used to replace dummy variables in ' +
                             'working config file')
    parser.add_argument('start_date',
                        help='first date of data to download, first' +
                             ' day of VIC simulation, YYYY-MM-DD. Note:' +
                             ' for MONITOR, this should be a date for ' +
                             'which there is a VIC state file')
    parser.add_argument('end_date',
                        help='last date of data to download, last ' +
                             'day of VIC simulation, YYYY-MM-DD')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)

    # get units conversion from cf_units for K to degC
    units_in = cf_units.Unit('K')
    units_out = cf_units.Unit('degC')

    # initial cdo
    cdo = Cdo()

    # read in meteorological data location
    old_config_file = config_dict['ECFLOW']['old_Config']
    new_config_file = config_dict['ECFLOW']['new_Config']
    n_days = int(config_dict['ECFLOW']['Met_Delay'])
    met_out = config_dict['MONITOR']['Orig_Met']

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # get current date and number of days
    # define the end date for subdaily generation and the vic run
    end_date_format = args.end_date
    end_date = datetime.strptime(end_date_format, '%Y-%m-%d')
    num_day = end_date.timetuple().tm_yday - 1  # python 0 start correction

    # get VIC start date and the date to save the state
    # the last 60 days in the met dataset are provisional, so we start our run
    # the day before the first provisional day
    vic_start_date_format = args.start_date
    vic_start_date = datetime.strptime(vic_start_date_format, '%Y-%m-%d')
    # python 0 start correction
    vic_start_date_num = vic_start_date.timetuple().tm_yday - 1
    # we save the state at the beginning of the first provisional day
    # would be the first day after start date if in automated system
    vic_save_state = end_date - timedelta(days=59)
    vic_save_state_format = vic_save_state.strftime('%Y-%m-%d')
    #vic_save_state_format = '2018-03-01'
    #vic_save_state = datetime.strptime(vic_save_state_format, '%Y-%m-%d')
    num_startofyear = 0
    if calendar.isleap(vic_start_date.year):
        num_endofyear = 365
    else:
        num_endofyear = 364

    # set a variable name for the number of lats and lons
    num_lat = 584
    num_lon = 1385

    # define variable names used when filling threads URL
    # an abbreviation and a full name is needed
    varnames = [('pr', 'precipitation_amount'), ('tmmn', 'air_temperature'),
                ('tmmx', 'air_temperature'), ('vs', 'wind_speed'),
                ('srad', 'surface_downwelling_shortwave_flux_in_air'),
                ('sph', 'specific_humidity')]

    # check if data we are downloading coms from multiple years
    # replace start date, end date and met location in the configuration file
    kwargs = {'START_DATE': vic_start_date_format,
              'END_DATE': end_date_format,
              'VIC_SAVE_STATE': vic_save_state_format,
              'MED_START_DATE': '-9999',
              'MED_END_DATE': '-9999',
              'MED_VIC_SAVE_STATE': '-9999',
              'SEAS_START_DATE': '-9999',
              'SEAS_END_DATE': '-9999',
              'SEAS_VIC_SAVE_STATE': '-9999',
              'FULL_YEAR': 'Year'}
    model_tools.replace_var_pythonic_config(old_config_file, new_config_file,
                                            header=None, **kwargs)
    met_dsets = dict()
    if vic_start_date.year != end_date.year:
        num_startofyear = 0
        if calendar.isleap(vic_start_date.year):
            num_endofyear = 365
        else:
            num_endofyear = 364
        # download metdata from http://thredds.northwestknowledge.net
        for var in varnames:
            url_thisyear = define_url(var, end_date.year, num_lon, num_lat,
                                      [num_startofyear, num_day])

            ds_thisyear = xr.open_dataset(url_thisyear)

            url_lastyear = define_url(var, vic_start_date.year, num_lon, num_lat,
                                      [vic_start_date_num, num_endofyear])
            ds_lastyear = xr.open_dataset(url_lastyear)

            # concatenate the two datasets and add general attributes
            xds = xr.concat([ds_lastyear, ds_thisyear], 'day')

            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds
    else:
        # download metdata from http://thredds.northwestknowledge.net
        for var in varnames:
            url = define_url(var, end_date.year, num_lon, num_lat,
                             [vic_start_date_num, num_day])
            # download data and add general attributes
            xds = xr.open_dataset(url)

            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds

    for var in ('tmmn', 'tmmx'):
        # Perform units conversion
        units_in.convert(met_dsets[var].air_temperature.values[:], units_out,
                         inplace=True)
        # Fix _FillValue after unit conversion
        met_dsets[var].air_temperature.attrs['units'] = "degC"
        met_dsets[var].air_temperature.values[
            met_dsets[var].air_temperature < -30000] = -32767.
        # Change variable names so that tmmn and tmax are different
        met_dsets[var].rename({'air_temperature': var}, inplace=True)
    merge_ds = xr.merge(list(met_dsets.values()))
    merge_ds.transpose('day', 'lat', 'lon')
    # MetSim requires time dimension be named "time"
    merge_ds.rename({'day': 'time'}, inplace=True)
    # add attributes
    #merge_ds = recreate_attrs(merge_ds)
    # Make sure tmax >= tmin always
    tmin = np.copy(merge_ds['tmmn'].values)
    tmax = np.copy(merge_ds['tmmx'].values)
    swap_values = ((tmin > tmax) & (tmax != -32767.))
    merge_ds['tmmn'].values[swap_values] = tmax[swap_values]
    merge_ds['tmmx'].values[swap_values] = tmin[swap_values]
    # write merge_ds to a temporary file so that we don't run into
    # issues with the system /tmp directoy filling up
    temporary = os.path.join(config_dict['ECFLOW']['TempDir'], 'met_out')
    merge_ds.to_netcdf(temporary)
    # conservatively remap to grid file
    cdo.remapcon(grid_file, input=temporary, output=met_out)
    os.remove(temporary)

if __name__ == "__main__":
    main()

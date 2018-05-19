#!/usr/bin/env python
"""
get_metstate.py
usage: <python> <get_metstate.py> <configuration.cfg>
This script downloads meteorological data through xarray from
http://thredds.northwestknowledge.net:8080/thredds/reacch_climate_MET_catalog.html
delivered through OPeNDAP. Because attributes are lost during download,
they are added back in. Gets 90 days prior to the subdaily met disaggregation
start time for use as state file for MetSim.
"""
import os
import argparse
import calendar
from collections import OrderedDict
from datetime import datetime, timedelta
import numpy as np
import xarray as xr
from cdo import Cdo
import cf_units

from tonic.io import read_config


def main():
    ''' get 90 days of gridMet data leading up to the first day of VIC
        simulation and formate as state file for use in MetSim. '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Download met state data')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)

    # Initialize Cdo class
    cdo = Cdo()

    # read in meteorological data location
    met_state = config_dict['MONITOR']['Met_State_File']

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # get dates to process
    state_end_date = datetime.strptime(
        config_dict['MONITOR']['Start_Date'], '%Y-%m-%d') - timedelta(
            days=1)
    state_end_date_format = state_end_date.strftime('%Y-%m-%d')
    state_end_date = datetime.strptime(state_end_date_format, '%Y-%m-%d')
    state_end_year = state_end_date.strftime('%Y')
    # python 0 start correction
    state_end_day_num = state_end_date.timetuple().tm_yday - 1
    # we need 90 days for MetSim
    state_start_date = state_end_date - timedelta(days=90)
    state_start_year = state_start_date.strftime('%Y')
    # python 0 start correction (-1)
    state_start_day_num = state_start_date.timetuple().tm_yday - 1
    num_startofyear = 0
    if calendar.isleap(int(state_start_year)):
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

    # since start and end are always 90 days apart, we never download data
    # from more than 2 calendar years
    if state_start_year != state_end_year:
        # download metdata from http://thredds.northwestknowledge.net
        met_dsets = dict()
        for var in varnames:
            url_endyear = ("http://thredds.northwestknowledge.net:8080" +
                           "/thredds/dodsC/MET/%s/%s_%s.nc?lon[0:1:%s]," % (
                               var[0], var[0], state_end_year, num_lon) +
                           "lat[0:1:%s],day[%s:1:%s]," % (
                               num_lat, num_startofyear, state_end_day_num) +
                           "%s[%s:1:%s]" % (
                               var[1], num_startofyear, state_end_day_num) +
                           "[0:1:%s][0:1:%s]" % (num_lon, num_lat))

            ds_endyear = xr.open_dataset(url_endyear)
            url_startyear = ("http://thredds.northwestknowledge.net:8080" +
                             "/thredds/dodsC/MET/%s/%s_%s.nc?lon[0:1:%s]," % (
                                 var[0], var[0], state_start_year, num_lon) +
                             "lat[0:1:%s],day[%s:1:%s]," % (
                                 num_lat, state_start_day_num, num_endofyear) +
                             "%s[%s:1:%s]" % (
                                 var[1], state_start_day_num, num_endofyear) +
                             "[0:1:%s][0:1:%s]" % (num_lon, num_lat))
            ds_startyear = xr.open_dataset(url_startyear)
            # concatenate the two datasets and add general attributes
            xds = xr.concat([ds_startyear, ds_endyear], 'day')
            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds

    else:  # if we have data from the same year, can download from same file.
        # download metdata from http://thredds.northwestknowledge.net
        met_dsets = dict()
        for var in varnames:
            url = ("http://thredds.northwestknowledge.net:8080" +
                   "/thredds/dodsC/MET/%s/%s_%s.nc?lon[0:1:%s]," % (
                       var[0], var[0], state_start_year, num_lon) +
                   "lat[0:1:%s],day[%s:1:%s]," % (
                       num_lat, state_start_day_num, state_end_day_num) +
                   "%s[%s:1:%s]" % (
                       var[1], state_start_day_num, state_end_day_num) +
                   "[0:1:%s][0:1:%s]" % (num_lon, num_lat))
            # download data and add general attributes
            xds = xr.open_dataset(url)
            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds
    for var in ('tmmn', 'tmmx'):
        # Perform units conversion from K to degC
        units_in = cf_units.Unit(met_dsets[var].air_temperature.attrs['units'])
        units_out = cf_units.Unit('degC')
        units_in.convert(met_dsets[var].air_temperature.values[:], units_out,
                         inplace=True)
        # Fix _FillValue after unit conversion
        met_dsets[var].air_temperature.values[
            met_dsets[var].air_temperature < -30000] = -32767.
        met_dsets[var].air_temperature.attrs['units'] = 'degC'
        # Change variable names so that tmmn and tmax are different
        met_dsets[var].rename({'air_temperature': var}, inplace=True)

    merge_ds = xr.merge(list(met_dsets.values()))
    merge_ds.transpose('day', 'lat', 'lon')
    # MetSim requires time dimension be named "time"
    merge_ds.rename({'day': 'time', 'tmmn': 't_min', 'tmmx': 't_max',
                     'precipitation_amount': 'prec'}, inplace=True)
    # Make sure tmax >= tmin always
    tmin = np.copy(merge_ds['t_min'].values)
    tmax = np.copy(merge_ds['t_max'].values)
    swap_values = ((tmin > tmax) & (tmax != -32767.))
    nswap = np.sum(swap_values)
    if nswap > 0:
        print('MINOR WARNING: tmax < tmin in {} cases'.format(nswap))
    merge_ds['t_min'].values[swap_values] = tmax[swap_values]
    merge_ds['t_max'].values[swap_values] = tmin[swap_values]
    # write merge_ds to a temporary file so that we don't run into
    # issues with the system /tmp directoy filling up
    temporary = os.path.join(config_dict['ECFLOW']['TempDir'], 'met_state')
    merge_ds.to_netcdf(temporary)
    # conservatively remap to grid file
    cdo.remapcon(grid_file, input=temporary, output=met_state)
    os.remove(temporary)


if __name__ == '__main__':
    main()

#!/usr/bin/env python
"""
usage: <python> <get_BC_metstate.py> <configuration.cfg>

Uses paramiko to transfer BC metdata netCDFs from the
NKN network.
"""
import os
import argparse
from datetime import datetime, timedelta
import paramiko
from cdo import Cdo
import cf_units
import numpy as np
import xarray as xr

from tonic.io import read_config


def main():
    ''' Download meteorological data for 90 days before the start of MetSim
        data from the Northwest Knowledge Network for British Columbia.
    '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Download met state data ' +
                                     'for British Columbia')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)

    # get units conversion from cf_units for K to degC
    units_in = cf_units.Unit('K')
    units_out = cf_units.Unit('degC')

    # initialize cdo
    cdo = Cdo()

    # read in meteorological data location
    met_out = config_dict['MONITOR']['Met_State_File']

    # read in the source and destination paths and current date
    source_loc = config_dict['MONITOR']['BC_Met_Source']
    dest_loc = os.path.dirname(met_out)

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # get dates to process
    state_end_date = datetime.strptime(
        config_dict['MONITOR']['Start_Date'],
        '%Y-%m-%d') - timedelta(days=1)
    state_end_date_format = state_end_date.strftime('%Y-%m-%d')
    state_end_date = datetime.strptime(state_end_date_format, '%Y-%m-%d')
    state_end_year = state_end_date.strftime('%Y')

    # we need 90 days for MetSim
    state_start_date = state_end_date - timedelta(days=90)
    state_start_date_format = state_start_date.strftime('%Y-%m-%d')
    state_start_year = state_start_date.strftime('%Y')

    # an abbreviation and a full name is needed
    varnames = [('pr', 'precipitation_amount'), ('tmmn', 'air_temperature'),
                ('tmmx', 'air_temperature'), ('vs', 'wind_speed'),
                ('srad', 'surface_downwelling_shortwave_flux_in_air'),
                ('sph', 'specific_humidity')]
    # set up a connection to the NKN network
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.load_host_keys(os.path.expanduser(
        os.path.join("~", ".ssh", "known_hosts")))
    ssh.connect('reacchdb.nkn.uidaho.edu', username='vicmet',
                password='cl!m@te')
    sftp = ssh.open_sftp()
    # access data files
    for year in range(int(state_start_year), int(state_end_year) + 1):
        # transfer the meteorological files
        for var in varnames:
            source_file = os.path.join(source_loc, '{0}_BC_{1}.nc'.format(
                var[0], year))
            local_file = os.path.join(dest_loc, '{0}_{1}.nc'.format(
                var[0], year))
            sftp.get(source_file, local_file)
    sftp.close()
    ssh.close()
    met_dsets = {}
    if state_start_year != state_end_year:
        for var in varnames:
            ds_lastyear = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], state_start_year)))
            ds_thisyear = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], state_end_year)))
            # concatenate the two datasets and add general attributes
            xds = xr.concat([ds_lastyear, ds_thisyear], 'day')

            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds
    else:
        for var in varnames:
            met_dsets[var[0]] = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], state_start_year)))
    for var in ('tmmn', 'tmmx'):
        # Perform units conversion
        units_in.convert(met_dsets[var].air_temperature.values[:], units_out,
                         inplace=True)
        # Fix _FillValue after unit conversion
        met_dsets[var].air_temperature.values[
            met_dsets[var].air_temperature < -30000] = -32767.
        # Change variable names so that tmmn and tmax are different
        met_dsets[var].rename({'air_temperature': var}, inplace=True)
    merge_ds = xr.merge(list(met_dsets.values()))
    merge_ds = merge_ds.loc[dict(day=slice(
        state_start_date_format, state_end_date_format))]
    merge_ds.transpose('day', 'lat', 'lon')
    # MetSim requires time dimension be named "time"
    merge_ds.rename({'day': 'time'}, inplace=True)
    # Make sure tmax >= tmin always
    tmin = np.copy(merge_ds['tmmn'].values)
    tmax = np.copy(merge_ds['tmmx'].values)
    swap_values = ((tmin > tmax) & (tmax != -32767.))
    nswap = np.sum(swap_values)
    if nswap > 0:
        print('MINOR WARNING: tmax < tmin in {} cases'.format(nswap))
    merge_ds['tmmn'].values[swap_values] = tmax[swap_values]
    merge_ds['tmmx'].values[swap_values] = tmin[swap_values]
    merge_ds['tmmn'].attrs['units'] = 'degC'
    merge_ds['tmmx'].attrs['units'] = 'degC'
    merge_ds = merge_ds.transpose('time', 'lat', 'lon')
    merge_ds.rename({'tmmn': 't_min', 'tmmx': 't_max',
                     'precipitation_amount': 'prec'}, inplace=True)
    # conservatively remap to grid file
    cdo.remapcon(grid_file, input=merge_ds, output=met_out)


if __name__ == "__main__":
    main()

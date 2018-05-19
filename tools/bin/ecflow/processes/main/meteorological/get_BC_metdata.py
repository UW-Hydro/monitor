#!/usr/bin/env python
"""
Get British Columbia met data
usage: <python> <get_BC_metdata.py> <configuration.cfg>

Uses paramiko to download meteorological data for British Columbia
from NKN network
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
from monitor import model_tools


def main():
    ''' Download meteorological data from NKN for British Columbia.
        Reformat to match U.S. met data and the format expected by
        MetSim '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Download met data for ' +
                                     'British Columbia')
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
    old_config_file = config_dict['ECFLOW']['old_Config']
    new_config_file = config_dict['ECFLOW']['new_Config']
    n_days = int(config_dict['ECFLOW']['Met_Delay'])
    met_out = config_dict['MONITOR']['Orig_Met']

    # read in the source and destination paths and current date
    source_loc = config_dict['MONITOR']['BC_Met_Source']
    dest_loc = os.path.dirname(met_out)

    # read in grid_file from config file
    grid_file = config_dict['DOMAIN']['GridFile']

    # get current date and number of days
    # define the end date for subdaily generation and the vic run
    end_date = datetime.now() - timedelta(days=n_days)
    end_date_format = end_date.strftime('%Y-%m-%d')

    # get VIC start date and the date to save the state
    # the last 60 days in the met dataset are provisional, so we start our run
    # the day before the first provisional day
    start_date = end_date - timedelta(days=60)
    start_date_format = start_date.strftime('%Y-%m-%d')
    # we save the state at the beginning of the first provisional day
    vic_save_state = start_date + timedelta(days=1)
    vic_save_state_format = vic_save_state.strftime('%Y-%m-%d')


    # check if data we are downloading comes from multiple years
    # replace start date, end date and met location in the configuration file
    kwargs = {'START_DATE': start_date_format,
              'END_DATE': end_date_format,
              'VIC_SAVE_STATE': vic_save_state_format}
    model_tools.replace_var_pythonic_config(old_config_file, new_config_file,
                                            header=None, **kwargs)
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
    ssh.connect('reacchdb.nkn.uidaho.edu', username='vicmet', password='cl!m@te')
    sftp = ssh.open_sftp()
    # access data files
    for year in range(start_date.year, end_date.year + 1):
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
    if start_date.year != end_date.year:
        for var in varnames:
            ds_lastyear = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], start_date.year)))
            ds_thisyear = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], end_date.year)))
            # concatenate the two datasets and add general attributes
            xds = xr.concat([ds_lastyear, ds_thisyear], 'day')

            # place data in dict, the variable abbreviation is used as key
            met_dsets[var[0]] = xds
    else:
        for var in varnames:
            met_dsets[var[0]] = xr.open_dataset(os.path.join(
                dest_loc, '{0}_{1}.nc'.format(var[0], start_date.year)))
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
    # clip to relevant dates
    merge_ds = merge_ds.loc[dict(day=slice(start_date_format,
                                           end_date_format))]
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
    # conservatively remap to grid file
    cdo.remapcon(grid_file, input=merge_ds, output=met_out)


if __name__ == "__main__":
    main()

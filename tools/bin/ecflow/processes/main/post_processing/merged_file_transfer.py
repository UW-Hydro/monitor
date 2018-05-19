#!/usr/bin/env python
'''
transferring percentile files
usage: <python> <merged_transfer_files.py> <configuration.cfg>

Uses paramiko to transfer percentile netCDFs to the
NKN network, along with a text file that includes the date.
The date is read from that file and displayed in the map subtitles.
'''
import os
import argparse
from datetime import datetime
import paramiko

from tonic.io import read_config


def main():
    ''' Upload merged percentile (US + BC) netCDF files to NKN network
        with text file that includes the simulation date '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Upload merged percentiles')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    parser.add_argument('time_horizon_type', help='MONITOR, MED_FCST, or '
                        'SEAS_FCST. Should correspond to section header in '
                        'config_file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)
    section = args.time_horizon_type
    # read in the source and destination paths and current date
    source_loc = config_dict[section]['Percentile_Merge_Loc']
    dest_loc = config_dict['PERCENTILES']['Percentile_Dest']
    date = config_dict[section]['End_Date']
    current_date = datetime.strptime(date, '%Y-%m-%d')
    month = current_date.strftime("%B_%-d").upper()[:3]

    # set up a connection to the NKN network
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.load_host_keys(os.path.expanduser(
        os.path.join("~", ".ssh", "known_hosts")))
    ssh.connect('reacchdb.nkn.uidaho.edu', username='vicmet', password='cl!m@te')
    sftp = ssh.open_sftp()

    # transfer the percentile files
    varnames = ['swe', 'sm', 'tm']
    for var in varnames:
        if date[-2:] == '01':
            sftp.put(
                os.path.join(
                    source_loc, 'vic-metdata_%spercentile_%s.nc' %
                    (var, date)), os.path.join(
                        dest_loc, 'vic-metdata_%spercentile_%s%s.nc' %
                        (var, month, str(1))))
        sftp.put(
            os.path.join(
                source_loc, 'vic-metdata_%spercentile_%s.nc' %
                (var, date)), os.path.join(
                    dest_loc, 'vic-metdata_%spercentile_CURRENT.nc' %
                    (var)))
        print(os.path.join(
            source_loc, 'vic-metdata_%spercentile_%s.nc' %
            (var, date)))
    for agg in ['7d', '15d', '30d', '60d', '90d', 'ccy', 'cwy']:
        sftp.put(
            os.path.join(
                source_loc, 'vic-metdata_ropercentile_%s_%s.nc' %
                (agg, date)), os.path.join(
                    dest_loc, 'vic-metdata_ropercentile_%s.nc' %
                    (agg)))
        print(os.path.join(
            source_loc, 'vic-metdata_ropercentile_%s_%s.nc' %
            (agg, date)))
    # create a .txt file to include the date
    fout = sftp.open(os.path.join(dest_loc, 'lastDate.txt'), 'w+')
    fout.write('%s/%s/%s' % (date[:4], date[5:7], date[8:10]))
    fout.close()

    sftp.close()
    ssh.close()


if __name__ == '__main__':
    main()

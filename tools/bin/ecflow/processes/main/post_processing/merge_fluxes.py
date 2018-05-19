''' merge_fluxes.py
usage: python merge_fluxes.py <config_file> <time_horizon_type>
usage note: time_horizon_type must be MONITOR. this script is called
by monitor/tools/bin/ecflow/processes/US/post_processing/percentiles.ecf.
It is needed in order to calculate accumulated runoff.

This script uses cdo.mergetime to combine VIC flux files into
a single file per year. It is written to append the most recent data
and also to overwrite any duplicate date with the most recent data.
'''
import os
import argparse
from datetime import datetime, timedelta
from cdo import Cdo

from tonic.io import read_config


def main():
    ''' Uses cdo.mergetime to combine VIC flux files, keeping the data from
        the first input file when dates overlap '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Merge VIC flux files in ' +
                                     'time to have one flux file per year')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    parser.add_argument('time_horizon_type', help='MONITOR: ' +
                        'Should correspond to section header in ' +
                        'config_file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)
    section = args.time_horizon_type
    if section != 'MONITOR':
        print('ERROR: section must be MONITOR. For forecasts use ' +
              'merge_forecast.py')
        exit(0)
    cdo = Cdo()
    # SKIP_SAME_TIME = 1 is required in order to ensure that data is taken from
    # the newer file (first file listed as input in mergetime) instead of the
    # existing file for the most recent (duplicated) day(s) because the newer
    # file will reflect any updates to the provisional met data
    cdo.env['SKIP_SAME_TIME'] = '1'
    # get dates for file names
    start_date_format = config_dict[section]['Start_Date']
    start_date = datetime.strptime(start_date_format, '%Y-%m-%d')
    end_date_format = config_dict[section]['End_Date']
    end_date = datetime.strptime(end_date_format, '%Y-%m-%d')
    vic_save_state_format = config_dict[section]['vic_save_state']
    vic_save_state = datetime.strptime(vic_save_state_format, '%Y-%m-%d')
    # data is read from and saved to the same directory
    vic_dir = config_dict[section]['OutputDirRoot']
    if end_date.year == start_date.year:
        # merge data into file from same year
        merged = os.path.join(vic_dir, 'fluxes.{}.nc'.format(
            start_date.year))
        vic_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(start_date_format))
        if os.path.isfile(merged) and os.path.isfile(vic_out):
            tmpout = os.path.join(config_dict['ECFLOW']['TempDir'],
                                  'merge{}.nc'.format(start_date.year))
            cdo.mergetime(input='{0} {1}'.format(vic_out, merged),
                          output=tmpout)
            # if MONITOR, VIC is run twice to save state 60 days prior to
            # current day for
            # initializing tomorrow's run, so there are 2 output file. By
            # design, the second
            # file will not overlap with the first file
            vic_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(
                vic_save_state_format))
            cdo.mergetime(input='{0} {1}'.format(vic_out, tmpout),
                          output=merged)
            os.remove(tmpout)
    else:
        vic_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(start_date_format))
        # first file should end at vic_save_state
        year = (vic_save_state - timedelta(days=1)).year
        if year < start_date.year:
            merged = os.path.join(vic_dir, 'fluxes.{}.nc'.format(year))
            if os.path.isfile(merged) and os.path.isfile(vic_out):
                tmp1 = os.path.join(config_dict['ECFLOW']['TempDir'],
                                    'temp_select{}.nc'.format(year))
                cdo.seltime(year, input=vic_out, output=tmp1)
                tmpout = os.path.join(config_dict['ECFLOW']['TempDir'],
                                      'temp_merge{}.nc'.format(year))
                cdo.mergetime(input='{0} {1}'.format(tmp1, merged),
                              output=tmpout)
                os.rename(tmpout, merged)
                os.remove(tmp1)
        # second file starts at vic_save_state
        vic_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(vic_save_state_format))
        for year in range(vic_save_state.year, end_date.year + 1):
            # merge data into file from same year
            merged = os.path.join(vic_dir, 'fluxes.{}.nc'.format(year))
            if os.path.isfile(merged) and os.path.isfile(vic_out):
                tmp1 = os.path.join(config_dict['ECFLOW']['TempDir'],
                                    'temp_select{}.nc'.format(year))
                cdo.seltime(year, input=vic_out, output=tmp1)
                tmpout = os.path.join(config_dict['ECFLOW']['TempDir'],
                                      'temp_merge{}.nc'.format(year))
                cdo.mergetime(input='{0} {1}'.format(tmp1, merged),
                              output=tmpout)
                os.rename(tmpout, merged)
                os.remove(tmp1)


if __name__ == "__main__":
    main()

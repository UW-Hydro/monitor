''' merge_forecasts.py
    usage: python merge_forecasts.py config_file time_horizon_type
    Uses cdo.mergetime to combine flux files into one file per year
    for forecasts. Because runoff percentiles are computed over time
    windows longer than forecasts, we merge forecasts with fluxes to create
    an annual forecast file '''
import os
import argparse
from datetime import datetime
from cdo import Cdo

from tonic.io import read_config


def main():
    ''' Uses cdo.mergetime to combine VIC flux files, keeping the data from the first
        input file when dates overlap '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Merge VIC flux files in ' +
                                     'time to have one flux file per year')
    parser.add_argument('config_file', metavar='config_file',
                        help='configuration file')
    parser.add_argument('time_horizon_type', help='MONITOR, MED_FCST, or ' +
                        'SEAS_FCST. Should correspond to section header in ' +
                        'config_file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)
    section = args.time_horizon_type
    cdo = Cdo()
    cdo.env['SKIP_SAME_TIME'] = '1'
    # get dates for file names
    start_date_format = config_dict[section]['Start_Date']
    start_date = datetime.strptime(start_date_format, '%Y-%m-%d')
    end_date_format = config_dict[section]['End_Date']
    end_date = datetime.strptime(end_date_format, '%Y-%m-%d')
    # data is read from and saved to the same directory
    vic_dir = config_dict[section]['OutputDirRoot']
    vic_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(start_date_format))
    if section == 'MED_FCST':
        prev_vic_dir = config_dict['MONITOR']['OutputDirRoot']
    elif section == 'SEAS_FCST':
        prev_vic_dir = config_dict['MED_FCST']['OutputDirRoot']
    if end_date.year == start_date.year:
        # merge data into file from same year
        merged_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(
            start_date.year))
        merged_in = os.path.join(prev_vic_dir, 'fluxes.{}.nc'.format(
            start_date.year))
        if os.path.isfile(merged_in) and os.path.isfile(vic_out):
            # keep values from previous sections
            cdo.mergetime(input='{0} {1}'.format(merged_in, vic_out),
                          output=merged_out)
    else:
        for year in range(start_date.year, end_date.year + 1):
            # merge data into file from same year
            merged_out = os.path.join(vic_dir, 'fluxes.{}.nc'.format(year))
            merged_in = os.path.join(prev_vic_dir, 'fluxes.{}.nc'.format(year))
            if os.path.isfile(merged_in) and os.path.isfile(vic_out):
                tmp1 = cdo.seltime(year, input=vic_out)
                cdo.mergetime(input='{0} {1}'.format(merged_in, tmp1),
                              output=merged_out)


if __name__ == "__main__":
    main()

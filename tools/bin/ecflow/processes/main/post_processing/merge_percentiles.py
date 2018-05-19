''' merge_percentiles.py
    usage: merge_percentiles.py config_file time_horizon_type
    Uses the British Columbia config file to get information for both
    BC and US.
    Merge percentiles of soil moisture, SWE, total moisture and runoff
    for the U.S. and Canadian portions of Columbia river into a single
    netcdf file '''
import os
import argparse
from cdo import Cdo

from tonic.io import read_config


def main():
    ''' Uses cdo.mergegrid and an empty template for the final grid to merge
        percentiles of sm, swe, and tm from the US and Canada into a single netcdf file '''
    # read in configuration file
    parser = argparse.ArgumentParser(description='Merge BC and US data')
    parser.add_argument('BCconfig_file', metavar='BCconfig_file',
                        help='BCconfiguration file')
    parser.add_argument('time_horizon_type', help='MONITOR, MED_FCST, or ' +
                        'SEAS_FCST. Should correspond to section header in ' +
                        'config_file')
    args = parser.parse_args()
    config_dict = read_config(args.BCconfig_file)
    section = args.time_horizon_type
    cdo = Cdo()
    date = config_dict[section]['End_Date']
    bcdir = config_dict[section]['Percentile_Loc']
    usdir = config_dict[section]['Percentile_US_Loc']
    template_dir = config_dict['DOMAIN']['PercentileTemplateDir']
    merge_dir = config_dict[section]['Percentile_Merge_Loc']
    varnames = ['sm', 'swe', 'tm']
    for var in varnames:
        file_name = 'vic-metdata_{0}percentile_{1}.nc'.format(var, date)
        merge_template = os.path.join(template_dir,
                                      'vic-metdata_{}percentile_blankmerge1.nc'.format(var))
        bc_file = os.path.join(bcdir, file_name)
        us_file = os.path.join(usdir, file_name)
        merge_out = os.path.join(merge_dir, file_name)
        temp_out = os.path.join(config_dict['ECFLOW']['TempDir'], file_name)
        cdo.mergegrid(input='{0} {1}'.format(merge_template, bc_file),
                      output=temp_out)
        cdo.mergegrid(input='{0} {1}'.format(temp_out, us_file), output=merge_out)
        os.remove(temp_out)
    # merge runoff percentiles
    for agg in ['7d', '15d', '30d', '60d', '90d', 'ccy', 'cwy']:
        file_name = 'vic-metdata_ropercentile_{0}_{1}.nc'.format(agg, date)
        merge_template = os.path.join(template_dir,
                                      'vic-metdata_ropercentile_blankmerge1.nc')
        bc_file = os.path.join(bcdir, file_name)
        us_file = os.path.join(usdir, file_name)
        merge_out = os.path.join(merge_dir, file_name)
        temp_out = os.path.join(config_dict['ECFLOW']['TempDir'], file_name)
        cdo.mergegrid(input='{0} {1}'.format(merge_template, bc_file),
                      output=temp_out)
        cdo.mergegrid(input='{0} {1}'.format(temp_out, us_file),
                      output=merge_out)
        os.remove(temp_out)

if __name__ == "__main__":
    main()

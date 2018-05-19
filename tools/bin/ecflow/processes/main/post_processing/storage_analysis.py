''' storage_analysis.py
    usage: python storage_analysis.py config_file time_horizon_type
    time_horizon_type is MONITOR, MED_FCST, or SEAS_FCST and corresponds
    to section header in config file
    This script calculates percentiles for total column soil moisture,
    snow water equivalent (SWE) and total moisture (soil moisture + SWE)
    relative to the base period of 1981-2010.
'''
import os
from datetime import datetime
import argparse
import numpy as np
from scipy import stats
import xarray as xr

from tonic.io import read_config


def run_percentileofscore(historical, current, var):
    ''' Remove bad data and run stats.percentileofscore(). For SWE,
        require that the historical mean and current value are both
        at least 10 mm '''
    xhist = historical[~np.isnan(historical)]
    xhist = xhist[xhist != -9999]
    if xhist.size:
        # apply 10mm threshold to SWE
        if (var == 'swe') and ((xhist.mean() < 10) or (current < 10)):
            return -9999
        return stats.percentileofscore(
            historical[~np.isnan(historical)], current)
    return -9999


def return_category(percentile):
    ''' Assign percentiles to categories to create a non-linear
        color bar corresponding to to the U.S. Drought Monitor '''
    if 0 <= percentile < 2:
        category = 0
    elif 2 <= percentile < 5:
        category = 1
    elif 5 <= percentile < 10:
        category = 2
    elif 10 <= percentile < 20:
        category = 3
    elif 20 <= percentile < 30:
        category = 4
    elif 30 <= percentile < 70:
        category = 5
    elif 70 <= percentile < 80:
        category = 6
    elif 80 <= percentile < 90:
        category = 7
    elif 90 <= percentile < 95:
        category = 8
    elif 95 <= percentile < 98:
        category = 9
    elif percentile >= 98:
        category = 10
    else:
        category = -9999
    return category


def main():
    ''' Calculate percentiles for SWE, total moisture (SWE + soil moisture)
        and soil moisture '''
    parser = argparse.ArgumentParser(
        description='Calculate storage percentiles')
    parser.add_argument('config_file', metavar='config_file',
                        help='the python configuration file, see template:'
                        ' /monitor/config/python_template.cfg')
    parser.add_argument('time_horizon_type', help='MONITOR, MED_FCST, or '
                        'SEAS_FCST. Should correspond to section header in '
                        'config_file')
    args = parser.parse_args()
    config_dict = read_config(args.config_file)
    section = args.time_horizon_type

    analysis_date = config_dict[section]['End_Date']
    if section == 'MONITOR':
        infile = os.path.join(
            config_dict[section]['OutputDirRoot'], 'fluxes.{}.nc'.format(
                config_dict[section]['vic_save_state']))
    else:
        infile = os.path.join(
            config_dict[section]['OutputDirRoot'], 'fluxes.{}.nc'.format(
                config_dict[section]['Start_Date']))
    print('open {}'.format(infile))
    curr_xds = xr.open_dataset(infile)
    # TODO: determine Oct1 flux file name in script instead of as input
    oct1_ds = xr.open_dataset(config_dict[section]['Oct1_flux_file'])
    print('open {}'.format(config_dict['PERCENTILES']['historic_VIC_out']))
    hist_xds = xr.open_dataset(config_dict['PERCENTILES']['historic_VIC_out'],
                               chunks={'lat': 100, 'lon': 100})
    # extract variables
    print('get the variables we actually want')
    curr_vals = {}
    today_xds = curr_xds.loc[dict(time=analysis_date)]
    day = int(today_xds.time.dt.dayofyear)
    title = {'swe': 'SWE', 'sm': 'Total column soil moisture',
             'tm': 'Total moisture storage'}
    # remove Oct. 1 SWE at start of water year to correct for perennial SWE
    date_unformat = datetime.strptime(analysis_date, '%Y-%m-%d')
    if date_unformat.month >= 10:
        oct_yr = date_unformat.year
    else:
        oct_yr = date_unformat.year - 1
    # extract variables
    print('get the variables we actually want')
    curr_vals['swe'] = (today_xds['OUT_SWE'] -
                        oct1_ds['OUT_SWE'].loc[dict(time='{}-10-01'.format(
                            oct_yr))].values)
    curr_vals['sm'] = today_xds['OUT_SOIL_MOIST'].sum(dim='nlayer',
                                                      skipna=False)
    curr_vals['tm'] = curr_vals['swe'] + curr_vals['sm']
    hist_xds = hist_xds.where(
        (hist_xds['time'].dt.dayofyear >= day - 2) &
        (hist_xds['time'].dt.dayofyear <= day + 2))
    for var in ['swe', 'sm', 'tm']:
        print('allocate percentiles memory for {}'.format(var))
        pname = '{}percentile'.format(var)
        percentiles = xr.Dataset({pname:
                                  (['lat', 'lon'],
                                   -9999 * np.ones(curr_vals[var].shape)),
                                  'category':
                                  (['lat', 'lon'],
                                   -9999 * np.ones(curr_vals[var].shape))},
                                 coords={'lon': curr_vals[var].lon,
                                         'lat': curr_vals[var].lat})
        print('calculate percentiles for {}'.format(var))
        percentiles[pname] = xr.apply_ufunc(
            run_percentileofscore, hist_xds[var], curr_vals[var],
            kwargs={'var': var}, input_core_dims=[['time'], []],
            dask='parallelized', output_dtypes=[float], vectorize=True)
        print('calculate category for {}'.format(var))
        percentiles['category'] = xr.apply_ufunc(return_category,
                                                 percentiles[pname],
                                                 dask='parallelized',
                                                 output_dtypes=[float],
                                                 vectorize=True)
        print('add attributes')
        percentiles[pname].attrs['_FillValue'] = -9999.
        percentiles['category'].attrs['_FillValue'] = -9999.
        percentiles.attrs['analysis_date'] = analysis_date
        percentiles.attrs['title'] = '{} percentiles'.format(title[var])
        percentiles.attrs['comment'] = ('Calculated from output from the'
                                        ' Variable Infiltration '
                                        'Capacity (VIC) Macroscale Hydrologic'
                                        ' Model')
        for attr in ['VIC_Model_Version', 'VIC_Driver',
                     'references', 'Conventions', 'VIC_GIT_VERSION']:
            percentiles.attrs[attr] = curr_xds.attrs[attr]
        print('save file')
        outfile = os.path.join(
            config_dict[section]['Percentile_Loc'],
            'vic-metdata_{0}_{1}.nc'.format(pname, analysis_date))
        percentiles.to_netcdf(outfile)
        print('{} saved'.format(outfile))


if __name__ == "__main__":
    main()

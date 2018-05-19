''' ro_analysis.py
    usage: python ro_analysis.py <config_file> <time_horizon_type>
    time_horizon_type is MONITOR, MED_FCST, or SEAS_FCST and corresponds
    to section header in config file
    This script calculates runoff percentiles for runoff aggregated over
    the 7, 15, 30, 60, or 90 days leading up to the analysis date. It
    also calculates runoff percentiles for runoff aggregated over the
    calendar year to analysis date and water year to analysis date.
    One netcdf file is output for each aggregation period. Percentiles
    are calculated relative to a base period from 1981-2010.
'''

import os
import calendar
from datetime import datetime
import argparse
import numpy as np
from scipy import stats
import xarray as xr

from tonic.io import read_config


# ----- Time functions ------
def water_year(xdate):
    ''' returns water year for Oct. - Sep. water year '''
    if xdate['time.month'] > 9:
        return xdate['time.year'] + 1
    return xdate['time.year']


def define_dayofyear(xds):
    ''' returns day of year with modification to align leap and non-leap
        years. this is used in determining which days to include in
        accumulation '''
    dayofyear = xds['time.dayofyear']
    if calendar.isleap(xds['time.year']):
        # reset so that 2-29 is same day of year as 2/28 and all other
        # days align with non-leap years
        if dayofyear >= 60:
            dayofyear = dayofyear - 1
    return dayofyear


#------- functions to sum daily to year-to-date ----
def get_ro_cytd(xds_runoff):
    ''' sum runoff from first of year. delete runoff from Feb. 29 so that
        all sums are consistent with a 365-day calendar '''
    xsum = xds_runoff.groupby(xds_runoff.time.dt.year).apply(
        lambda xsum: xsum.cumsum(dim='time', skipna=False))
    for year in np.unique(xds_runoff.time.dt.year):
        if calendar.isleap(year):
            first = '{}-02-29'.format(year)
            last = '{}-12-31'.format(year)
            xsum.loc[dict(time=slice(first, last))] = (
                xsum.loc[dict(time=slice(first, last))] -
                xds_runoff.loc[dict(time=first)].values)
    return xsum


def get_ro_wytd(xds_runoff):
    ''' sum runoff from first of water year. delete runoff from Feb. 29 so that
        all sums are consistent with a 365-day calendar '''
    xsum = xds_runoff.groupby(xds_runoff.water_year).apply(
        lambda xsum: xsum.cumsum(dim='time', skipna=False))
    for year in np.unique(xds_runoff.water_year):
        if calendar.isleap(year):
            first = '{}-02-29'.format(year)
            last = '{}-09-30'.format(year)
            # only remove runoff for same water year, which ends Sep. 30
            xsum.loc[dict(time=slice(first, last))] = (
                xsum.loc[dict(time=slice(first, last))] -
                xds_runoff.loc[dict(time=first)].values)
    return xsum


# ----- Percentile/display functions ------
def run_percentileofscore(historical, current):
    ''' Runs stats.percentileofscore with checks for nan values '''
    if not np.isnan(current):
        return stats.percentileofscore(
            historical[~np.isnan(historical)], current)
    return np.nan


def return_category(percentile):
    ''' Returns categories for mapping percentiles to U.S. Drought
        Monitor event classification/colors '''
    if percentile < 2:
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
        category = np.nan
    return category

def initialize_percentile(analysis_date, lats, lons, attr_dict, agg):
    ''' initialize xarray dataset to hold percentile information '''
    nlat = len(lats)
    nlon = len(lons)
    percentiles = xr.Dataset({'ropercentile':
                              (['lat', 'lon'],
                               np.nan * np.ones([nlat, nlon])),
                              'category':
                              (['lat', 'lon'],
                               np.nan * np.ones([nlat, nlon]))},
                             coords={'lon': lons, 'lat': lats})
    for varname in percentiles.variables.keys():
        percentiles[varname].attrs['_FillValue'] = np.nan
    percentiles.attrs['analysis_date'] = analysis_date
    if agg == 'ccy':
        percentiles.attrs['title'] = ('Current calendar year runoff ' +
                                      'percentiles')
    elif agg == 'cwy':
        percentiles.attrs['title'] = ('Current water year runoff ' +
                                      'percentiles')
    else:
        percentiles.attrs['title'] = '{}-day runoff percentiles'.format(agg)
    percentiles.attrs['comment'] = ('Calculated from output from the' +
                                    ' Variable Infiltration ' +
                                    'Capacity (VIC) Macroscale Hydrologic'
                                    ' Model')
    for attr in ['VIC_Model_Version', 'VIC_Driver',
                 'references', 'Conventions', 'VIC_GIT_VERSION']:
        percentiles.attrs[attr] = attr_dict[attr]
    return percentiles


def main():
    ''' Calculate runoff percentiles for aggregations 7, 15, 30, 60, 90 days
        and current water year to date and current calendar year to date '''
    parser = argparse.ArgumentParser(description=
                                     'Calculate runoff percentiles')
    parser.add_argument('config_file', metavar='config_file',
                        help='the python configuration file, see template:' +
                        ' /monitor/config/python_template.cfg')
    parser.add_argument('time_horizon_type',
                        help='MONITOR, MED_FCST or SEAS_FCST')
    args = parser.parse_args()
    section = args.time_horizon_type
    config_dict = read_config(args.config_file)

    analysis_date_format = config_dict[section]['End_Date']
    analysis_date = datetime.strptime(analysis_date_format, '%Y-%m-%d')
    curr_year_xds = xr.open_dataset(os.path.join(
        config_dict[section]['OutputDirRoot'], 'fluxes.{}.nc'.format(
            analysis_date.year)))
    curr_year_runoff = (curr_year_xds['OUT_RUNOFF'] +
                        curr_year_xds['OUT_BASEFLOW'])
    last_year_xds = xr.open_dataset(os.path.join(
        config_dict[section]['OutputDirRoot'], 'fluxes.{}.nc'.format(
            analysis_date.year - 1)))
    last_year_runoff = (last_year_xds['OUT_RUNOFF'] +
                        last_year_xds['OUT_BASEFLOW'])
    curr_runoff = xr.concat([last_year_runoff, curr_year_runoff], dim='time')
    hist_xds = xr.open_dataset(config_dict['PERCENTILES']['historic_VIC_out'])
    hist_xds = hist_xds.loc[dict(time=slice('1981-01-01', '2010-01-01'))]
    # extract runoff
    hist_runoff = hist_xds['ro']

    # Calculate water years
    curr_runoff['water_year'] = curr_runoff.groupby('time').apply(water_year)
    hist_runoff['water_year'] = hist_runoff.groupby('time').apply(water_year)
    curr_runoff['dayofyear'] = curr_runoff.groupby('time').apply(
        define_dayofyear)
    hist_runoff['dayofyear'] = hist_runoff.groupby('time').apply(
        define_dayofyear)

    lats = curr_year_xds.lat
    lons = curr_year_xds.lon
    shared_attrs = curr_year_xds.attrs
    day = curr_runoff['dayofyear'].loc[dict(time=analysis_date_format)]
    for agg in [7, 15, 30, 60, 90]:
        print('process {} days'.format(agg))
        curr = curr_runoff.rolling(time=agg).sum()
        hist = hist_runoff.rolling(time=agg).sum()
        today = curr.loc[dict(time=analysis_date_format)]
        subset = hist.where((hist_runoff['dayofyear'] >= day - 2) &
                            (hist_runoff['dayofyear'] <= day + 2))
        percentiles = initialize_percentile(analysis_date_format, lats,
                                            lons, shared_attrs,
                                            agg)
        percentiles['ropercentile'] = xr.apply_ufunc(run_percentileofscore,
                                                     subset, today,
                                                     input_core_dims=[
                                                         ['time'], []],
                                                     vectorize=True)
        percentiles['category'] = xr.apply_ufunc(return_category,
                                                 percentiles['ropercentile'],
                                                 vectorize=True)
        percentiles.to_netcdf(os.path.join(
            config_dict[section]['Percentile_Loc'],
            'vic-metdata_ropercentile_{0}d_{1}.nc'.format(
                agg, analysis_date_format)))
    for agg, get_ro in zip(['cwy', 'ccy'], [get_ro_wytd, get_ro_cytd]):
        print('process {}'.format(agg))
        curr = get_ro(curr_runoff)
        hist = get_ro(hist_runoff)
        today = curr.loc[dict(time=analysis_date_format)]
        subset = hist.where((hist_runoff['dayofyear'] >= day - 2) &
                            (hist_runoff['dayofyear'] <= day + 2))
        percentiles = initialize_percentile(analysis_date_format, lats,
                                            lons, shared_attrs,
                                            'ccy')
        percentiles['ropercentile'] = xr.apply_ufunc(run_percentileofscore,
                                                     subset, today,
                                                     input_core_dims=[['time'],
                                                                      []],
                                                     vectorize=True)
        percentiles['category'] = xr.apply_ufunc(return_category,
                                                 percentiles['ropercentile'],
                                                 vectorize=True)
        percentiles.to_netcdf(os.path.join(
            config_dict[section]['Percentile_Loc'],
            'vic-metdata_ropercentile_{0}_{1}.nc'.format(
                agg, analysis_date_format)))


if __name__ == "__main__":
    main()

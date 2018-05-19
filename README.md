Monitor
=======
`monitor` is a near real-time monitor of environmental conditions,
designed to be run through the work flow package ecFlow.

## Overview:
Monitor has three main components.

**Meteorological**  `/monitor/tools/bin/ecflow/processes/main/meteorological/`
	Contains scripts for the manipulation of meteorological data, 
including to download, regrid, and generate subdaily forcings.

**Models**  `/monitor/tools/bin/ecflow/processes/main/models/`
	Contains scripts to conduct model runs. Initial implementation
uses the model `VIC`.

**Post-Processing**  `/monitor/tools/bin/ecflow/processes/main/post_processing/`
	Contains scripts to analyze the model output. 

## Requirements:  
- python 2.7 (ecflow dependency)
- numpy
- scipy
- matplotlib
- pandas
- xarray
- netCDF4
- configobj
- basemap
- paramiko
- datetime
- os
- argparse
- cdo
- python-cdo
- nco
- pynco
- dask

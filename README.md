# SeismicMatch documentation
```
                          _                       __        
                         / \               _   __/  \       __
          /\            /   \       _     / \_/      \     /  \       _
_____/\  /  \_/\_______/     \     / \   /            \   /    \     / \___
       \/                     \   /   \_/              \_/      \   /
                               \_/                               \_/
```

- [Installation](#installation)
- [Workflow](#workflow)
- [File formats](#file-formats)
- [Data example (tutorial)](#example-data-tutorial)
- [References](#references)

## Installation:

This software is designed to run on an NVIDIA GPU and makes use of the CUDA
toolkit. If no NVIDIA graphics card is available, or if the user whishes so,
SeismicMatch can also run in full CPU mode. 

### From source:

Create a conda environment with python3 installed:
```console
>>> conda create -n SM python=3
```
#### Install dependencies:

```console
>>> conda install numpy==1.23.5 scipy pyyaml
>>> conda install -c conda-forge obspy
>>> conda install -c conda-forge cupy
```
Note that the installation of cupy requires the CUDA toolkit, and the CuPy
version depends on the CUDA driver. Conda should automatically pick the right
version, but a table is also provided on the [CuPy website](https://docs.cupy.dev/en/stable/install.html).

If CuPy can not be installed, SeismicMatch can also run in full CPU mode, albeit
less efficient.

#### Install SeismicMatch:

Move inside the SeismicMatch project folder that contains "setup.py" and run the
installation script (requires pip and setuptools).
```console
>>> cd ~/Downloads/SeismicMatch
>>> pip install .
```

## Workflow

This is an overview of the normal SeismicMatch workflow. Before starting you own
project, it is also possible to play around with the [example data](#example-data-tutorial) described below.

The prerequisites for starting a new project are:
- continuous data obervations in a format readable by ObsPy
- a starting catalog for which templates should be extracted
- a station metadata file (channel level) for the selection of stations to be used
  in StationXML format

Before you start, make sure that SeismicMatch is installed and the virtual
environment in which it is installed is activated. Next, choose a location for
your new project and create a project folder.

```console
>>> mkdir my_tm_project
>>> cd my_tm_project
```

### 1. Project configuration
To start a new project, we need to create project configuration file. This file
must be located in the root of our project folder and must be called `config.yaml`.
We can create a new configuration file with default settings using the command-
line tool `create_config`

```console
>>> create_config
```

This creates `config.yaml` in the current working directory. Open the file using
your preferred editor and change the parameters to your needs. A description of
all fields is provided at the bottom of the file. The performance settings are
automatically detected when a new configuration file is created and are therefore
specific to your machine.

Note that changes to this file after extracting the template waveforms in the next
step may cause problems, since preprocessing is applied permanently to the template
waveforms. Changing the preprocessing values after template extraction will cause
the continuous data to be preprocessed differently.

### 2. Template extraction
The next step is to extract template waveforms for the starting catalog of events
using the command-line tool `create_templates`.

```console
>>> create_templates my_starting_catalog.xml
```

Note that the starting catalog should be in a format readable by ObsPy. This will
create a folder where template waveforms will be stored. The location of this folder
as well as the (pre-processing) settings for the template waveforms are defined in
the configuration file. Additionally, individual event files are created in the events
folder.

If no templates are being created, please check that the continuous data is provided
in the data folder, that the data structure and filenames are correctly defined
in the configuration file, and data is available for the events in the starting
catalogue. Add the command-line argument `-vvv` to increase the verbosity for debugging.

### 3. Template matching
Now, we can start the main template matching script using the command-line
`match_templates`. It is possible to specify specific template waveforms as command-
line arguments:

```console
>>> match_templates *template_waveforms
```

If no specific template waveforms are provided as command-line arguments, all template
waveforms in the template folder are used by default:

```console
>>> match_templates
```

The template waveforms will now be cross-correlated with the continuous data in
the data folder, for the time-span defined in the configuration file.

### 4. Event families
The command-line tool `create_event_families` combines the matches from each individual
template waveform and applies the selection criteria defined in the configuration file.
If a set of simultaneous matches meets these criteria, an event is appended to the
template family of the template event. It is possible to specify specific match files as
command-line arguments:

```console
>>> creat_event_families *match_files
```

If no specific match files are provided as command-line arguments, all match files in the
matches folder are used by default:

```console
create_event_families
```

Note that if an event is detected using multiple template events, it will appear in multiple
event families. This creates a list of event detections for each template event in the event
folder. The filenames of the event family files match the filenames of the template event
files in the event folder.

## File formats:

### Continuous data:
The continuous data must be in a [format readable by ObsPy](https://docs.obspy.org/packages/autogen/obspy.core.stream.read.html#supported-formats),
where each file represents data from a single channel on a single day. The data should be
structured in a way that the filename (including the path) contains the network code, station
code, location code, channel code and the julian day as a 3-digit number. This data structure
needs to be defined in the configuration file.

### Station metadata:
The station metadata needs to be provided in StationXML format at the channel level. This format
is provided by all [FDSN webservices](https://www.fdsn.org/xml/station/).

### Starting catalog:
The starting catalog should be in a [format readable by ObsPy](https://docs.obspy.org/packages/autogen/obspy.core.event.read_events.html#supported-formats).

### Event files:
Individual event files are created in the event folder for each template event. The filenames
are a representation of the event origin time as defined in the starting catalog. This identifier
is also used in the template waveform files. This way, matches can easily be recombined with
template information to construct event detections. The event files are written in QuakeML format
to support all event information contained in the starting catalog.

### Match files:
The filenames of the match files are a combination of the waveform identifier, the template
event identifier, and the number of samples in the template waveform: `waveformid_evid_nsamples`.
Each file contains the instances where a single template waveform passes the cross-correlation
threshold with the corresponding continuous data. The files consist of 4 columns, separated by
spaces. Each line represents a single detection. The columns represent the detection time (time
that aligns with the starttime of the template waveform), the maximum normalized cross-correlation
coefficient, the cross-correlation coefficient expressed as a factor of the mean absolute deviation
(MAD) of the daily cross-correlation funcion, and the amplitude ratio of the detected event compared
to the template event waveform.

Example match file `example_data/matches/CX.PB01..HHZ_2021005T032907.3800Z_1076`:
```
2021005T004454.6183Z 0.755 20.582 5.327E-02
2021005T032928.7783Z 1.000 27.262 9.999E-01
2021005T033907.2983Z 0.869 23.685 2.634E-01
2021005T035238.8983Z 0.916 24.971 1.086E-01
2021005T115025.3783Z 0.814 22.190 5.558E-02
```

### Event family files:
The filenames of the event family files correspond to the template event files in the event folder,
and are a representation of the template events origin time. The files consit of 5 columns, separated
by spaces. Each line represents an event detection. The columns represent the estimated event origin
time, a comma separated list of channels contributing to the detection, a comma separated list of the
normalized cross-correlation values for each channel, a comma separated list of the MAD values for
each channel, and a comma separated list of the amplitude ratios for each channel.

Example event family file `example_data/event_families/2021005T032907.3800Z`:
```
2021-01-05T00:44:33.220000Z CX.PB02..HHZ,CX.PB11..HHZ,CX.PSGCX..HHZ,CX.PB01..HHZ 0.899,0.940,0.926,0.755 25.288,29.297,23.823,20.582 5.557E-02,5.364E-02,5.179E-02,5.327E-02
2021-01-05T03:29:07.380000Z CX.PSGCX..HHZ,CX.PB11..HHZ,CX.PB01..HHZ,CX.PB02..HHZ 1.000,1.000,1.000,1.000 25.722,31.176,27.262,28.137 1.000E+00,1.000E+00,9.999E-01,1.000E+00
2021-01-05T03:38:45.900000Z CX.PSGCX..HHZ,CX.PB11..HHZ,CX.PB02..HHZ,CX.PB01..HHZ 0.885,0.880,0.852,0.869 22.774,27.425,23.973,23.685 2.220E-01,2.035E-01,2.332E-01,2.634E-01
2021-01-05T03:41:44.819907Z CX.PSGCX..HHZ,CX.PB02..HHZ 0.764,0.779 19.657,21.924 3.183E-02,3.567E-02
2021-01-05T03:52:17.540000Z CX.PB11..HHZ,CX.PSGCX..HHZ,CX.PB02..HHZ,CX.PB01..HHZ 0.913,0.950,0.934,0.916 28.448,24.448,26.289,24.971 1.159E-01,1.109E-01,1.144E-01,1.086E-01
2021-01-05T11:50:03.979907Z CX.PSGCX..HHZ,CX.PB11..HHZ,CX.PB01..HHZ,CX.PB02..HHZ 0.896,0.890,0.814,0.914 23.035,27.741,22.190,25.711 5.267E-02,6.075E-02,5.558E-02,5.405E-02

```

## Example data (tutorial):

The SeismicMatch installation folder contains a directory `example_data` that
can be used to follow allong with this example. First, move to this directory.

```console
>>> cd ~/Downloads/SeismicMatch
>>> cd example_data
```

Next, we need to create a configuration file.

```console
>>> create_config
```

This creates the project configuration file (`config.yaml`) containing all 
parameters and data descriptors. This configuration file is read by all scripts
that are executed from within this folder. The default settings in the configuration
file are already suitable for the example data, and do not need to be changed.
The performance settings at the top of the configuration file are automatically
detected from your machine.

This folder contains sample data from the [*CX*](#references) network in northern Chile
for a single day in the folder `data_CX`. The `metadata` folder contains
station metadata (`stations.xml`) for each of the stations. The file
`sippl_catalog_sample.xml` contains a sample from the IPOC seismicity catalog
for northern Chile ([Sippl et al., 2023](https://doi.org/10.5880/GFZ.4.1.2023.004)).

The first step is to extract template waveforms for the events in the sample
catalog using the script `create_templates`.

```console
>>> create_templates sippl_catalog_sample.xml
```

This creates a two folders `templates` and `events` within the project
directory. The config file `config.yaml` allows you to define different names
and locations, as well as to set all the relevant parameter settings.
- preprocessed template waveforms will be written to the `templates` folder
  in MSEED format.
- individual event files will be written to the `events` folder.

The template waveforms can now be cross-correlated with the continuous data in
the data folder. The data folder contains data for a single day, which is also
reflected in the the time-span defined in the configuration file.

```console
>>> match_templates
```

This starts the template matching. Note that SeismicMatch is designed to handle
large data volumes efficiently. Small projects such as in this example do not
reflect its performance very well, especially using GPUs. The example is merely
intended to demonstrate the workflow and test different settings.

A file is created for each template waveform in the folder `matches`, containing
a list of all instances where the cross-correlation threshold is passed.

Finally, we can combine the matches from the individual template waveforms into
event families. An event family represents a set of event detections that are
related to a single template event using the criteria defined in the configuration
file.

```console
>>> create_event_families
```

This creates a list of event detections for each template event in the folder
`event_families`. The filenames of the event family files match the filenames
of the template event files in the `events` folder.

### References
> [Sippl et al., 2023] Sippl, C., Schurr, B., Münchmeyer, J., Barrientos, S., and Oncken, O. (2023). The
northern chile forearc constrained by 15 years of permanent seismic monitoring. Journal of South American
Earth Sciences, 126:104326.
> 
> GFZ German Research Centre for Geosciences; Institut des Sciences de l’Univers-Centre National de la
Recherche CNRS-INSU (2006): IPOC Seismic Network. Integrated Plate boundary Observatory Chile - IPOC.
Dataset/Seismic Network. doi:10.14470/PK615318.

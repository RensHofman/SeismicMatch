# -*- coding: utf-8 -*-

import os
import yaml
import datetime
import logging

from seismic_match import common

logger = logging.getLogger(__name__)

class Config:

    def __init__(self):
        """Read the configuration file.

        The file should be named config.yaml and exist in the current
        working directory.

        """
        try:
            with open('%s/config.yaml' % os.getcwd(), 'r') as f:
                config = yaml.safe_load(f)
        except FileNotFoundError as e:
            raise Exception("Configuration file config.yaml "
                            f"not found:\n\n{e}")
        except (yaml.parser.ParserError, yaml.scaner.ScannerError):
            logger.error("Could not parse config.yaml. Please check"
                         " the file for errors or create a new one.")
            raise
        self.config_file = f.name
        self.validate_config(config)
        self.parse_config(config)

        # set flag whether to use cupy or not
        self.use_cupy = self.n_gpu > 0

    def parse_config(self, config):
        """Parse the contents of config.yaml."""
        # performance settings:
        settings = config['performance']
        self.n_cpu = settings['n_cpu']
        self.n_gpu = settings['n_gpu']
        self.cuda_devices = settings['cuda_devices']

        # template settings
        settings = config['templates']
        self.n_stations = settings['n_stations']
        self.channel = settings['channel']
        self.prepick = settings['prepick']
        self.min_win_len = settings['min_len']
        self.length_fixed = settings['length_fixed']
        self.temp_data_path = settings.get(
                                'template_data_path',
                                config['directories']['data_path'])
        self.temp_data_structure = settings.get(
                                    'template_data_structure',
                                    config['directories']['data_structure'])

        # pre-processing settings
        settings = config['pre_processing']
        self.fmin = settings['highpass']
        self.fmax = settings['lowpass']
        self.decimation_factor = settings['decimate']

        # cross-correlation settings
        settings = config['cross_correlation']
        self.data_start = settings['data_start']
        self.data_stop = settings['data_stop']
        self.cc_threshold = settings['cc_threshold']
        self.mad_threshold = settings['mad_threshold']
        self.combine_thresholds = settings['combine_thresholds']

        # folders and file structure
        settings = config['directories']
        self.meta_dir = settings['meta_dir']
        self.event_dir = settings['event_dir']
        self.template_dir = settings['template_dir']
        self.matches_dir = settings['matches_dir']
        self.family_dir = settings['family_dir']
        self.data_path = settings['data_path']
        self.data_structure = settings['data_structure']

        # event selection criteria
        settings = config['selection']
        self.cc_criteria = sorted(settings['cc_criteria'])[::-1]
        self.mad_criteria = sorted(settings['mad_criteria'])[::-1]
        self.max_t_diff = settings['max_t_diff']
        self.combine_criteria = settings['combine_criteria']

    def validate_config(self, config):
        """Validate the parameters read from the configuration file."""

        errors = []
        default = DefaultConfig()
        # check parameter existence, type and range
        for section, pars in default.parameters.items():
            if not section in config:
                config[section] = dict()
            for par, (required, par_type, par_range, default) in pars.items():
                if par not in config.get(section):
                    if required:
                        errors.append(f"Required parameter '{par}' in "
                                      f"section {section} is missing.")
                    elif default is not None:
                        config[section][par] = default
                    else:
                        continue
                value = config[section][par]
                if not isinstance(value, par_type):

                    if isinstance(par_type, tuple):
                        par_type = par_type[0]
                    errors.append(f"Parameter '{par}' in section "
                                  f"{section} should be of "
                                  f"type {par_type.__name__}, not "
                                  f"{type(value).__name__}.")
                    continue
                if isinstance(value, list) and par_range is not None:
                    for element in value:
                        if not (par_range[0] <= element <= par_range[1]):
                            errors.append(f"Elements in list '{par}' in "
                                          f"section {section} should "
                                          f"be in range {par_range}.")
                            break
                elif par_range is not None:
                    if not (par_range[0] <= value <= par_range[1]):
                        errors.append(f"Parameter '{par}' in "
                                      f"section {section} should "
                                      f"be in range {par_range}.")

        # raise errors here before checking paramater consistency
        if errors:
            raise ValueError("The configuration file (config.yaml) "
                             f"contains {len(errors)} error(s):\n\n" +
                             "\n".join(errors))

        # check consistency of performance parameters
        if config['performance']['n_gpu'] > 0:
            n_gpu = common.gpu_count()
            if config['performance']['n_gpu'] > n_gpu:
                errors.append("The parameter 'n_gpu' was set to "
                              f"{config['performance']['n_gpu']} but "
                              "{fn_gpu} GPU(s) could be discovered. Setting "
                              f"value to {n_gpu}.")
            if not 'cuda_devices' in config['performance']:
                config['performance']['cuda_devices'] = (
                    list(range(config['performance']['n_gpu'])))
            if (len(config['performance']['cuda_devices']) != 
                    config['performance']['n_gpu']):
                errors.append("The list of CUDA devices provided in "
                              "'cuda_devices' does not match the number "
                              "of GPUs in the parameter 'n_gpu'. "
                              "If you don't wish to specify devices, you "
                              "can delete this parameter.")
            for dev_id in config['performance']['cuda_devices']:
                if not isinstance(dev_id, int):
                    errors.append("The values in 'cuda_devices' should be "
                                  " of type int, not {type(dev_id).__name__}.")
                if dev_id >= n_gpu:
                    errors.append(f"The value '{dev_id}' in the list "
                                  "'cuda_devices' is out of range for this "
                                  "machine. The available devices are: "
                                  f"{list(range(n_gpu))}. If you don't wish "
                                  "to specify devices, you can delete this "
                                  "parameter.")

        # check consistency of filter settings
        if (config['pre_processing']['highpass'] >=
                config['pre_processing']['lowpass']):
            errors.append("Parameter 'lowpass' should be greater "
                          "than 'highpass'.")

        # check consistency of cross-correlation and selection parameters
        if config['selection']['cc_criteria']:
            if (min(config['selection']['cc_criteria']) <
                    config['cross_correlation']['cc_threshold']):
                errors.append("The values in `cc_criteria` cannot be below "
                              "the initial cross-correlation threshold "
                              "'cc_threshold'.")
        if config['selection']['mad_criteria']:
            if (min(config['selection']['mad_criteria']) <
                    config['cross_correlation']['mad_threshold']):
                errors.append("The values in `mad_criteria` cannot be below "
                              "the initial cross-correlation threshold "
                              "'mad_threshold'.")
        if (config['cross_correlation']['data_start'] >
                config['cross_correlation']['data_stop']):
            errors.append("The strart date for cross-correlation 'cc_start' "
                          "cannot be after the end date 'cc_end'.")

        if errors:
            raise ValueError("The configuration file (config.yaml) "
                             f"contains {len(errors)} error(s):\n\n" +
                             "\n".join(errors))
        # raise parameter consistency errors
        else:
            logger.debug(f"Successfully read config file {self.config_file} "
                         "with no errors.")

def create_example_config():
    """Create a config file with default settings for the example data."""
    if os.path.exists('config.yaml'):
        raise FileExistsError(
                "A file called 'config.yaml' already exists in the "
                "current working directory. Please rename or delete "
                "this file or move to a different folder."
                )
    default = DefaultConfig()
    with open('config.yaml', 'w') as f:
        f.write(default.config_header)
        for section, params in default.parameters.items():
            f.write(f"# {section} settings\n")
            f.write(f"{section}:\n")
            for name, (_, _, _, value) in params.items():
                if value is not None:
                    f.write(f"    {name}: {value}\n")
            f.write("\n")
        f.write(default.parameter_descriptions)
    logger.info("New config file config.yaml was created")
    # This validates the config immediately
    Config()


class DefaultConfig():
    """Container for the default configuration settings and info."""

    def __init__(self):
        # param_name: (required, type, valid range, default value)
        self.parameters = {
        'performance': {
            'n_cpu': (False, int, (1, 500), common.cpu_count()),
            'n_gpu': (False, int, (0, 50), common.gpu_count()),
            'cuda_devices': (False, list, None,
                             list(range(common.gpu_count()))),
            },
        'templates': {
            'n_stations': (True, int, (1, 100), 4),
            'channel': (False, str, None, 'HHZ'),
            'prepick': (True, (float, int), (0, 10), 3),
            'min_len': (True, (float, int), (5, 100), 15),
            'length_fixed': (True, bool, None, False),
            'template_data_path': (False, str, None, None),
            'template_data_structure': (False, str, None, None),
            },
        'pre_processing': {
            'highpass': (True, (float, int), (0, 100), 1.),
            'lowpass': (True, (float, int), (0.0, 100), 4.),
            'decimate': (True, int, (0, 10), 4),
            },
        'cross_correlation': {
            'data_start': (True, datetime.date, None, '2021-01-05'),
            'data_stop': (True, datetime.date, None, '2021-01-05'),
            'cc_threshold': (True, (float, int), (0, 1), .7),
            'mad_threshold': (True, (float, int), (0, 100), 8),
            'combine_thresholds': (True, bool, None, True),
            },
        'directories': {
            'meta_dir': (True, str, None, 'metadata'),
            'event_dir': (True, str, None, 'events'),
            'template_dir': (True, str, None, 'templates'),
            'matches_dir': (True, str, None, 'matches'),
            'family_dir': (True, str, None, 'event_families'),
            'data_path': (True, str, None, 'data_CX'),
            'data_structure': (True, str, None,
                               '"{data_path}/{year}/{net}/{sta}/{cha}.D/\\\n\
                     {net}.{sta}.{loc}.{cha}.D.{year}.{julday}"'),
            },
        'selection': {
            'cc_criteria': (True, list, (0, 1), [.7, .7]),
            'mad_criteria': (True, list, (0, 100), []),
            'max_t_diff': (True, (float, int), None, 10.),
            'combine_criteria': (True, bool, None, True),
            }
        }

        self.config_header = """\
#   config.yaml
#
#   This is a config file for the example data. It can be used as a
#   starting point for creating a custom config file for your project.
#   Please read the parameter descriptions at the bottom of this file.

"""

        self.parameter_descriptions = """
#   parameter descriptions:
#
#   performance settings:
#   These settings control the performance of SeismicMatch. When the
#   configuration file is created, the optimal settings are automatically
#   detected from your system. If you wish to use full CPU mode, set
#   'n_gpu' to 0. This is the default setting if no graphics card is available.
#       n_cpu (int, optional): maximum number of parallel processes to be
#           used. Defaults to the number of cpu cores.
#       n_gpu (int, optional): maximum number of graphics cards to use. By
#           default, all graphics cards will be used.
#       cuda_devices (list, optional): specify which CUDA devices should be
#           used. By default, the first 'n_gpu' devices will be used.
#
#   template settings:
#       n_stations (int, required): the number of stations for which to extract
#           templatewaveforms. These will be the closest available stations
#           to the event hypocenter.
#       channel (str, optional): channel code to be used. The use of multiple
#           channels is currently not supported. Defaults to 'HHZ'.
#       prepick (float, required): starttime of the template windows relative
#           to the estimated P-wave arrival in seconds.
#       min_len (float, required): minimum length of the template waveforms in
#           sec. The templates will be lengthened with 5 second increments for
#           increasing hypocentral distance.
#       length_fixed (bool, required): if set to True, all template waveforms
#            will have the same length determined by `min_len`.
#       template_data_path (str, optional): path to the folder that holds the
#           continuous data from which templates should be extracted if this
#           path is required to be different from the general data path.
#           Defaults to the data_path under 'folders and file structure'.
#       template_data_structure (str, optional): description of the data
#           structure (folders & filenames) within 'template_data_path'.
#           Placeholders can (and should) be used to include the data folder,
#           year, netowrk code, station code, location code, channel code and
#           the julian day in curly brackets: {data_path}, {year}, {net},
#           {sta}, {loc}, {cha}, {loc}, {julday}. Defaults to the
#           'data_structure' as defined under 'folders and file structure'.
#
#   pre-processing settings:
#       highpass (float, required): lower frequency in Hz of the bandpass
#           filter applied to both the templates (permanent) and continuous
#           data (upon loading).
#       lowpass (float, required): upper frequency in Hz of the bandpass filter
#           applied to both the templates (permanent) and continuous data (upon
#           loading).
#       decimate (int, required): the factor by which the sampling rate of the
#           data should be lowered (for faster computation). Decimation will be
#           applied permanently to the templates and dynamically to the
#           continuous data upon loading.
#
#   cross-correlation settings:
#       data_start (yyyy-mm-dd, required): starting date for cross-correlation
#           of the templates with the continous data.
#       data_stop (yyyy-mm-dd, required): last date to be included in the
#           cross-correlation.
#       cc_threshold (float, required): threshold of the absolute normalized
#           cross-correlation value.
#       mad_threshold (float, required): threshold of the normalized cross-
#           correlation value as a factor of the daily median absolute
#            deviation (MAD).
#       combine_thresholds (bool, required): if True, both thresholds need to
#           be passed. If False, only one threshold needs to be passed.
#
#   folders and file structure:
#   Path names are defined either absolute, or relative to the project
#   folder containing this configuration file.
#       meta_dir (str, required): path to the metadata folder that holds the
#           station xml file `stations.xml` containing the station information.
#       event_dir (str, required): path to the folder where event information
#           is stored. Single event catalog files will be created here to
#           which the template files and event families can be traces back
#           to through their filenames.
#       template_dir (str, required): path to the folder where template
#           waveforms will be stored.
#       matches_dir (str, required): path to the folder where all matches to
#           each individual template waveform are stored.
#       family_dir (str, required): path to the folder where event detections
#           that exceed the selection criteria are stored for each template
#           event. Note that the same event can occur within multiple event
#           families.
#       data_path (str, required): path to the folder that holds the
#           continuous data.
#       data_structure (str, required): description of the data structure
#           (folders & filenames) within `data_path`. Placeholders can (and
#           should) be used to include the data folder, year, netowrk code,
#           station code, location code, channel code and the julian day in
#           curly brackets: {data_path}, {year}, {net}, {sta}, {loc}, {cha},
#           {loc}, {julday}.
#
#   event selection criteria:
#       cc_criteria (list of floats, required): selection criteria to define an
#           event in terms of the absolute normalized cross-correlation value.
#           For example: [0.7, 0.5] would mean that two simultaneous
#           matches with absolute cross-correlation values >= 0.7 & >= 0.5
#           on two different stations are required within the time range
#           `max_t_diff`. Use an empty list `[]` if no cc-criteria should
#           be applied.
#       mad_criteria (list of floats, required): selection criteria to define
#           an event in terms of a factor of the daily median absolute
#           deviation (MAD) of the normalized cross-correlation function.
#           For example: [10, 8] would mean that two simultaneous matches
#           with 10x and 8x the daily MAD value are required within the
#           time range `max_t_diff`. Use an empty list `[]` if no MAD-
#           criteria should be applied.
#       max_t_diff (float, required): maximum time difference in seconds
#           between individual detections that allows them to be called
#           simultaneous for the purpose of the selection criteria defined
#           above. Note that the time difference relates to the estimated
#           origin time of the detections and not the actual occurrence of
#           the template waveforms, since these would depend on the
#           stations hypocentral distance.
#       combine_criteria (bool): if True, both the `cc_criteria` as well as
#           the `mad_criteria` need to be met. If set to False an event is
#           defined when either of both criteria are met.
"""

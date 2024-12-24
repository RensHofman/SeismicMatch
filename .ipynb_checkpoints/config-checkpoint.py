# -*- coding: utf-8 -*-

import os
from yaml import safe_load as load

class Config:
    
    def __init__(self):
        """Read the configuration file.
    
        The file should be named config.yaml and exist in the current
        working directory.
    
        """
        with open('%s/config.yaml' % os.getcwd(), 'r') as f:
            config = load(f)
            self.read_config(config)
    
    def read_config(self, config):
        """Parse the contents of config.yaml."""
        # template matching
        self.cc_start = config['templates']['cc_start']
        self.cc_stop = config['templates']['cc_stop']
        
        # template settings
        self.cc_threshold = config['templates']['cc_threshold']
        self.mad_threshold = config['templates']['mad_threshold']
        self.prepick = config['templates']['prepick']
        self.min_win_len = config['templates']['min_len']
        self.fmin = config['templates']['highpass']
        self.fmax = config['templates']['lowpass']
        self.n_stations = config['templates']['n_stations']
        self.decimation_factor = config['templates']['decimate']
        
        # file structure
        self.data_path = config['files']['data_path']
        self.data_structure = config['files']['data_structure']
        self.template_dir = config['files']['template_dir']
        self.event_dir = config['files']['event_dir']
        self.matches_dir = config['files']['matches_dir']
        self.meta_dir = config['files']['meta_dir']
        
def create_config():
    """Create a config file with default settings.
    
    For orientation purposes only, the values should be editd.

    """
    pass

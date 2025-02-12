# -*- coding: utf-8 -*-
"""
Create a default configuration file that can be adapted
to the project needs.

The file will be created in the current working directory
and be called config.yaml. A description of the parameters
can be found at the bottom of the config file.

Usage:
    create_config
"""
import argparse
import multiprocessing as mp

from seismic_match.config import create_example_config
from seismic_match.common import setup_logging

def main():

    args = parse_args()
    logger = setup_logging(args.verbosity, __name__)
    create_example_config()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help=("Change output verbosity (default is info, "
                              "use -v for errors, -vv for warnings, "
                              "-vvv for debug)."))
    return parser.parse_args()


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()

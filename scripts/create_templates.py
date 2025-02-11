#! /home/rens/miniconda3/envs/obspy/bin/python
"""
create_templates.py

Usage:
    create_templates input_catalog

Arguments:
    input_catalog: ObsPy readable event catalog in QuakeML format
"""

import argparse
import os
import logging
import multiprocessing as mp

import numpy as np
from obspy import Catalog
from obspy import read_events

from seismic_match.common import (chunks, template_name,
                                  event_name, setup_logging)
from seismic_match.data_handling import DataHandler
from seismic_match.config import Config

def main():
    """Create template waveforms.

    Extract templates for the closest n_stations stations for all
    events in the catalog. Travel-times are calculated for straight
    rays using a fixed value for P and S wave velocity.
    """
    args = parse_args()
    setup_logging(args.verbosity)
    
    catalog = read_events(args.input_catalog)
    config = Config()

    logging.info(f"Creating templates for {len(catalog)} events "
                 f"in {args.input_catalog} on {config.n_stations} "
                 "stations per event")

    # create project folders
    if not os.path.exists(config.template_dir):
        os.makedirs(config.template_dir)
    if not os.path.exists(config.event_dir):
        os.makedirs(config.event_dir)

    with mp.Pool(processes=config.n_cpu) as pool:
        chunksize = int(np.ceil(len(catalog) / config.n_cpu))
        events = chunks(catalog.events, chunksize)
        stats = pool.starmap(
                    create_templates,
                    [(ev_list, config, args.verbosity)
                         for ev_list in events])
    n_new, n_exist = np.array(stats).sum(axis=0)

    logging.info(f"Finished creating templates for {args.input_catalog}.")
    logging.info(f"Result: {n_new} new templates, {n_exist} pre-existing.")

def create_templates(event_list, config, verbosity):
    """Create template waveforms and event files for the events in the list."""
    setup_logging(verbosity)
    dh = DataHandler(config)
    n_new, n_exist = 0, 0
    for event in event_list:
        st = dh.create_template_traces(event)
        if not st:
            continue
        logging.debug(f"{len(st)} candidate stream(s) for event on "
                     f"{event.origins[0].time.ctime()}.")
        for tr in st:
            temp_name = template_name(tr, event)
            fname = f'{config.template_dir}/{temp_name}'
    
            if os.path.exists(fname):
                logging.debug(f"Template already exists in {temp_name}.")
                n_exist += 1
                continue
            tr.stats['mseed'].pop('encoding', None)
            tr.write(fname, format='MSEED')
            logging.debug(f"Created new template {temp_name}.")
            n_new += 1
            
            ev_cat = f"{config.event_dir}/{event_name(event)}"
            Catalog(events=[event]).write(ev_cat, format='QUAKEML')
    
    return n_new, n_exist


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('input_catalog',
                        help='Input catalog for templates.')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help=("Change output verbosity (default is info, "
                              "use -v for errors, -vv for warnings, "
                              "-vvv for debug)."))
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()

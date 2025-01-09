#! /home/rens/miniconda3/envs/CUDA/bin/python

import sys
import os
import argparse
import numpy as np
import multiprocessing as mp
import time
import logging

from seismic_match.data_handling import DataHandler
from seismic_match.template_matching import TemplateMatcher
from seismic_match.config import Config
from seismic_match.common import setup_logging, chunks


def main():
    """Correlate templates with continuous data.

    The continuous data window is
    chosen automatically based on previously processed data.
    """
    args = parse_args()
    setup_logging(args.verbosity)
    config = Config()

    if not os.path.exists(config.matches_dir):
        os.makedirs(config.matches_dir)

    logging.info("Scanning template- and match-files.")
    if not args.template_files:
        args.template_files = os.listdir(config.template_dir)
    else:
        args.template_files = [path.split('/')[-1] for path in
                               args.template_files]

    # remove templates that already have match-files from input
    matches = os.listdir(config.matches_dir)
    template_files = [t for t in args.template_files if t not in matches]
    if not template_files:
        logging.info("No unprocessed templates found.")
        return

    # split files into groups for same channel and template length
    template_groups = list(group_by_channel_length(template_files))

    logging.info("Starting template matching.")
    # launch template matcher using multiple GPUs and a CPU pool
    if config.n_gpu > 1:
        chunksize = int(np.ceil(len(template_groups) / config.n_gpu))
        temp_lists = chunks(template_groups, chunksize)
        with mp.Manager() as manager:
            with manager.Pool(processes=config.n_cpu) as pool:
                args = [(temps, config, args.verbosity, cuda_device, pool)
                        for temps, cuda_device in zip(temp_lists,
                                                      config.cuda_devices)]
                pool.starmap(tm_worker, args)
    # launch template matcher for a single GPU or full CPU mode
    else:
        dh = DataHandler(config)
        with mp.Pool(processes=config.n_cpu) as pool:
            tm = TemplateMatcher(config, dh, pool)
            if config.use_cupy:
                tm.set_cuda_device(config.cuda_devices[0])
            for templates in template_groups:
                tm.match_templates(templates)

    logging.info("Finished matching templates.")


def tm_worker(templates, config, verbosity, cuda_device, pool):
    setup_logging(verbosity)
    dh = DataHandler(config)
    tm = TemplateMatcher(config, dh, pool)
    tm.set_cuda_device(cuda_device)
    for temps in templates:
        tm.match_templates(temps)


def sort_unique(times):
    """Return a sorted list of unique datetime instances in times."""
    list_out = []
    for t in times:
        if t not in list_out:
            list_out.append(t)
    list_out.sort()
    return list_out


def group_by_channel(template_files):
    """Split the list of templates into list for each unique channel."""
    channel_list = [['none']]
    for f in sorted(template_files):
        cha = f.split('_')[0]
        if cha not in channel_list[-1][-1]:
            channel_list.append([])
        channel_list[-1].append(f)
    return channel_list[1:]


def group_by_channel_length(template_files):
    """Sort template files.

    Split the list of templates into list for each unique
    channel_template-length combination.
    """
    # numpy array with cha, temp_id, npts columns
    template_files = np.array(np.char.split(template_files,
                                            sep='_').tolist())
    channels = set(template_files[:, 0])
    for cha in channels:
        cha_temps = template_files[np.where(template_files[:, 0] == cha)]
        lengths = set(cha_temps[:, 2])
        for temp_len in lengths:
            subset = cha_temps[np.where(cha_temps[:, 2] == temp_len)]
            yield ['_'.join(temp) for temp in subset]


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('template_files',
                        nargs='*',
                        help='Template files for cross-correlation.')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help=("Change output verbosity (default is info, "
                              "use -v for errors, -vv for warnings, "
                              "-vvv for debug)."))
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()

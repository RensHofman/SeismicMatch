# -*- coding: utf-8 -*-
"""
This module contains useful functions that are used throughout the
project.
"""
import logging
from itertools import islice
import multiprocessing as mp


def template_name(tr, event):
    """Return a filename for the given template trace."""
    return ('%s_%s_%i' % (
            tr.id,
            event.origins[0].time.format_fissures(),
            tr.stats.npts))

def event_name(event):
    """Return a filename for the given event."""
    return event.origins[0].time.format_fissures()


def cpu_count():
    """Return the number of cpu cores."""
    return mp.cpu_count()


def gpu_count():
    """Count the number of gpu cards in a separate process."""
    mp.set_start_method('spawn', force=True)
    with mp.Pool(1) as pool:
        n_gpu = pool.apply(count_cuda_devices)
    return n_gpu

def count_cuda_devices():
    """Return the number of gpu cards."""
    try:
        import cupy as cp
    except ModuleNotFoundError:
        return 0
    return cp.cuda.runtime.getDeviceCount()


def chunks(data, N):
    """Yield N-sized chunks from data."""
    # prevents endless loop if data is not iterator or generator
    data = iter(data)
    while True:
        chunk = list(islice(data, N))
        if not chunk:
            break
        yield chunk


def setup_logging(verbosity):
    """Setup a logger."""
    verbosity_levels = {
        1: logging.ERROR,    # No messages
        2: logging.WARNING,  # Only warnings
        0: logging.INFO,     # Info mode
        3: logging.DEBUG     # Debug mode
    }

    log_level = verbosity_levels.get(verbosity, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
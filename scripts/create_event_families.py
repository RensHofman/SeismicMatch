#! /home/rens/miniconda3/envs/obspy/bin/python

import sys
import os
import argparse
import multiprocessing as mp
import logging

import numpy as np
from obspy import read
from obspy import read_events
from obspy import UTCDateTime

from seismic_match.config import Config
from seismic_match.common import setup_logging, chunks

def main():

    config = Config()
    args = parse_args()
    setup_logging(args.verbosity)

    if not os.path.exists(config.family_dir):
        os.makedirs(config.family_dir)

    logging.info("Scanning detection files.")
    if not args.detection_files:
        args.detection_files = os.listdir(config.matches_dir)
    else:
        args.detection_files = [path.split('/')[-1] for path in
                                args.detection_files]

    logging.info("Merging detections into event families.")
    detections = list(sort_detection_files(args.detection_files))
    chunksize = int(np.ceil(len(detections) / config.n_cpu))
    detections = chunks(detections, chunksize)
    with mp.Pool(processes=config.n_cpu) as pool:
        pool.starmap(process_detections,
                     [(temps, config, args.verbosity) for temps in detections])
    logging.info("Finished merging detections.")

def process_detections(detections, config, verbosity):
    """Merge detections into events by applying criteria and write to files."""
    setup_logging(verbosity)
    for temp_detections in detections:
        event_detections = event_list(config, temp_detections)
        event_detections = merge(config, event_detections)
        events = apply_criteria(config, event_detections)
        ev_id = temp_detections[0, 1]
        n = -1
        with open(f'{config.family_dir}/{ev_id}', 'w') as f:
            for n, ev in enumerate(events):
                f.write(f'{" ".join(ev.astype(str))}\n')
        logging.debug(f"Found {n+1} events for template {ev_id}.")



def sort_detection_files(detection_files):
    """Sort files by template id and return a list of Arrays."""
    detections = np.array([f.split('_') for f in detection_files])
    for ev_id in set(detections[:, 1]):
        yield detections[detections[:, 1] == ev_id]


def event_list(config, detections):
    """Return a sorted numpy array of template detections."""
    events = []
    for i, detection in enumerate(detections):
        detection_f = '_'.join(detection)
        template_f = f'{config.template_dir}/{detection_f}'
        origin_time = iso_date(detection[1])
        st = read(template_f, headonly=True)
        sta_id = detection[0]

        # time difference between event and template window
        dt = st[0].stats.starttime - origin_time

        # read detections
        ev_detections = np.loadtxt(f'{config.matches_dir}/{detection_f}',
                                   dtype=str)
        if ev_detections.ndim == 1:
            ev_detections = np.atleast_2d(ev_detections)
        timestamps = np.array([iso_date(t) for t in ev_detections[:, 0]])
        # convert detection time to origin time
        timestamps -= dt
        events += [np.column_stack((timestamps,
                                    np.array([sta_id]*len(ev_detections)),
                                    ev_detections[:, 1:],
                                    ))]
    events = np.vstack(events)
    return events[events[:, 0].argsort()]


def merge(config, event_detections):
    """Merge simultaneous detections."""
    n_rows, n_cols = event_detections.shape
    if n_rows < 2:
        return event_detections
    timestamps = [str(t) for t in event_detections[:, 0]]
    while True:
        # time difference between subsequent detections
        dt = event_detections[1:, 0] - event_detections[:-1, 0]
        merge_mask = dt <= config.max_t_diff
        # if no events left to be merged
        if np.all(~merge_mask):
            # pick timestamp corresponding to largest cc value for detection
            for i, t in enumerate(timestamps):
                cc = [float(cc) for cc in event_detections[i, 2].split(',')]
                cc_max = np.argmax(np.abs(cc))
                timestamps[i] = t.split(',')[cc_max]
            return np.column_stack((timestamps, event_detections[:, 1:]))
        for i, merge in enumerate(merge_mask):
            if not merge:
                continue
            for col in range(1, n_cols):
                event_detections[i+1, col] += f',{event_detections[i, col]}'
            timestamps[i+1] += f',{timestamps[i]}'
        # delete detections that have been merged
        del_mask = np.concatenate((merge_mask, [False]))
        event_detections = event_detections[~del_mask]
        timestamps = [t for t, _del in zip(timestamps, del_mask) if not _del]


def apply_criteria(config, detections):
    """Return detections that meet criteria."""
    for det in detections:
        if not config.combine_criteria:
            if (meets_cc_criteria(config, det) or
                meets_mad_criteria(config, det)):
                yield det
        else:
            if (meets_cc_criteria(config, det) and
                meets_mad_criteria(config, det)):
                yield det

        
def meets_cc_criteria(config, det):
    """Return True if the detection meets the cc criteria."""
    if not config.cc_criteria:
        return True
    cc_abs = np.sort(np.abs(np.fromstring(det[2], sep=',')))[::-1]
    if len(cc_abs) < len(config.cc_criteria):
        return False
    if not np.all(cc_abs[:len(config.cc_criteria)] >= config.cc_criteria):
        return False
    return True


def meets_mad_criteria(config, det):
    """Return True if the detection meets the mad criteria."""
    if not config.mad_criteria:
        return True
    mad = np.sort(np.fromstring(det[3], sep=','))[::-1]
    if len(mad) < len(config.mad_criteria):
        return False
    if not np.all(mad[:len(config.mad_criteria)] >= config.mad_criteria):
        return False
    return True


def iso_date(s):
    """Force iso8601 format on UTCDateTime."""
    return UTCDateTime(s, iso8601=True)


def master_event(event_dir, master_id):
    """Return the template event with the given id."""
    path = f'{event_dir}/{master_id}'
    if not os.path.exists(path):
        return None
    return read_events(path)[0]


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('detection_files',
                        nargs='*',
                        default=[])
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help=("Change output verbosity (default is info, "
                              "use -v for errors, -vv for warnings, "
                              "-vvv for debug)."))
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()

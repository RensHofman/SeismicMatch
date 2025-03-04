# -*- coding: utf-8 -*-
"""
This module contains the DataHandler class that contains all methods
used for reading and writing of waveform data.
"""
import os
import re
import sys
from glob import glob
import logging
from datetime import timedelta

import numpy as np
from obspy import read
from obspy import Stream
from obspy import read_inventory
from obspy.geodetics import gps2dist_azimuth

logger = logging.getLogger(__name__)

# Fallback to numpy if cupy is not available
cp = np

class DataHandler:

    def __init__(self, config):
        """Initiate the data handler by reading the configurations."""
        self.config = config
        self.inventory = read_inventory(f'{config.meta_dir}/stations.xml')

        if self.config.use_cupy:
            global cp
            import cupy as _cp
            cp = _cp

    def create_template_traces(self, event):
        """Create template waveforms for event.

        Create an ObsPy Stream object containing event traces for the
        closest stations around the event epicenter that have high
        enough signal to noise ratios. Maximum n_stations.

        Parameters
        ----------
        event : obspy event object
            The event for which template wavefrorms should be extracted.

        Returns
        -------
        templates : list of obspy stream objects
            A list of template waveforms extracted for the given event
            according to the settings in the config file.

        """
        templates = Stream()
        stations, distances = self.find_closest_stations(
                                    event,
                                    self.inventory,
                                    self.config.n_stations * 2)
        n_streams = 0
        for sta_id, distance in zip(stations, distances):
            net, sta, loc, cha = sta_id.split('.')
            station = self.inventory.select(network=net,
                                            station=sta,
                                            location=loc,
                                            channel=cha)[0][0]
            window = self.phase_window(event, station, distance)
            st = self.cut_template(net, sta, loc, cha, window)
            if len(st) == 0:
                logger.debug(f"Could not extract template for {sta_id}.")
                continue
            if self.snr_check(st):
                templates += st
                n_streams += 1
            else:
                logger.debug(f"Station {sta_id} has insufficient SNR.")
            if n_streams == self.config.n_stations:
                break
        if n_streams == 0:
            logger.warning("No template waveforms could be extracted"
                           f" for event on {event.origins[0].time.ctime()}")

        return templates

    def find_closest_stations(self, event, inventory, n_stations):
        """Find stations located around the event hypocenter.

        Return a list of the closest n_stations stations that have
        data available for the given event, as well as a list of their
        epicentral distances in km. If n_stations = 0 or None, the complete
        list of sorted stations and distances will be returned.

        Parameters
        ----------
        event : obspy event object
            Event around which stations should be searched for.
        inventory : obspy inventory object
            Station inventory metadata.
        n_stations : int
            Number of stations to return.

        Returns
        -------
        stations: list of station inventory objects
            List of closest stations around the event.
        distances: list of floats
            Approximate hypocentral distances in km to the stations.
        """
        if n_stations == 0:
            n_stations = None

        distances = []
        stations = []
        origin = event.origins[0]
        for net in inventory:
            for sta in net:
                cha = sta.select(channel=self.config.channel)[0]
                loc = cha.location_code
                fname = self.construct_data_path(
                            net.code, sta.code,
                            loc, cha.code,
                            origin.time.year,
                            origin.time.julday,
                            '*',
                            path_attr='temp_data_path',
                            structure_attr='temp_data_structure')
                try:
                    st = read(fname, headonly=True)
                    tr = st[0]
                except FileNotFoundError:
                    logger.debug(f"Station {sta.code} has no data "
                                 "for this day.")
                    continue
                except Exception as e:
                    logger.error(f"Could not read trace {fname}:\n{e}")
                    continue
                if (tr.stats.starttime > origin.time - 2 or
                        tr.stats.endtime < (origin.time +
                                            self.config.min_win_len)):
                    logger.debug(f"Station {sta.code} has no data within "
                                 "the event window.")
                    continue
                distances.append(
                    gps2dist_azimuth(
                        sta.latitude, sta.longitude,
                        origin.latitude, origin.longitude)[0] / 1e3)
                stations.append(f'{net.code}.{sta.code}.{loc}.{cha.code}')

        closest_stations = [stations[index] for index in np.argsort(distances)]
        return closest_stations[:n_stations], sorted(distances)[:n_stations]

    def cut_template(self, net, sta, loc, cha, window):
        """Extract a template waveform.

        Return a preprocessed Stream for the given station
        around the given time window.
        """
        st = Stream()
        data = [self.construct_data_path(
                    net, sta, loc, cha,
                    window[0].year,
                    window[0].julday,
                    '*',
                    path_attr='temp_data_path',
                    structure_attr='temp_data_structure')]
        if window[0].julday != window[1].julday:
            data += [self.construct_data_path(
                        net, sta, loc, cha,
                        window[1].year,
                        window[1].julday,
                        '*',
                        path_attr='temp_data_path',
                        structure_attr='temp_data_structure')]
        for f in data:
            tr = self.read_and_filter_trace(f)
            if tr is not None:
                st += tr

        st.trim(window[0], window[1])
        st.detrend(type='constant')
        return st

    def snr_check(self, st, sta=10, lta=100, snr_threshold=4):
        """Check if the SNR of the Stream is above the minimum."""
        for tr in st:
            if len(tr.data) < lta:
                st.remove(tr)
        if len(st) == 0:
            return False
        snr = st.copy().trigger('classicstalta', nsta=sta, nlta=lta)
        min_snr = min(snr.max())
        # if any of the traces does not meet minimum SNR threshold
        if min_snr < snr_threshold:
            return False
        peaks = [np.argmax(tr.data) for tr in snr]
        tr_len = len(st[0])
        # if any trace has the largest signal in the margins of the trace
        if min([min(pi, tr_len-pi) for pi in peaks]) < tr_len / 10:
            return False
        return True

    def prepare_data_list(self, waveform_id, start, end):
        """Return a list of dayfiles."""
        net, sta, loc, cha = waveform_id.split('.')

        d_files = glob(self.construct_data_path(
                    net, sta, loc, cha, '*', '*', '*',
                    ))
        files_in_range = []
        date = start
        days_requested = 0
        while date <= end:
            pattern = self.construct_data_path(
                        net, sta, loc, cha,
                        date.year,
                        date.strftime('%j'),
                        '.*',
                        )
            regex = re.compile(pattern)
            for fname in d_files:
                if regex.match(fname):
                    files_in_range += [fname]
                    break
            days_requested += 1
            date += timedelta(days=1)

        logger.debug(
            f"{len(files_in_range)}/{days_requested} dayfiles available "
            f"within the requested timespan (channel {waveform_id}).")

        return files_in_range

    def read_bulk_data(self, files, pool=None, method='assume_equal_length',
                  bandpass=True):
        """Return an array of preprocessed trace objects."""
        # read data in parallel
        if pool is not None:
            if bandpass:
                data_tr = pool.map(self.read_and_filter_trace, files)
            else:
                data_tr = pool.map(self.read_trace, files)
        # read data serially
        else:
            if bandpass:
                data_tr = [self.read_and_filter_trace(f) for f in files]
            else:
                data_tr = [self.read_trace(f) for f in files]

        # remove traces that could not be read
        data_tr = [tr for tr in data_tr if tr is not None]
        if not data_tr:
            return None, None

        if method == 'assume_equal_length':
            data = [cp.array(tr.data, dtype=cp.float32) for tr in data_tr]
            t_data = [tr.stats.starttime for tr in data_tr]

        elif method == 'make_equal_length':
            max_len = max([tr.stats.npts for tr in data_tr])
            data = cp.zeros((len(data_tr), max_len), dtype=cp.float32)
            for i, tr in enumerate(data_tr):
                for j, x in enumerate(tr.data):
                    data[i, j] = x
            t_data = [tr.stats.starttime for tr in data_tr]

        elif method == 'as_list':
            t_data = []

        return data, t_data

    def read_trace(self, f):
        """Return the first preprocessed trace of the obspy Stream object."""
        try:
            logger.debug(f"Reading trace file {f}.")
            st = read(f, dtype=np.float32, format='MSEED')
            tr = st[0]
        except Exception as e:
            logger.error(f"Could not read trace {f}:\n{e}")
            return None
        return tr

    def read_and_filter_trace(self, f):
        """Return the first preprocessed trace of the obspy Stream object."""
        tr = self.read_trace(f)
        self.filter_trace(tr)
        return tr

    def filter_trace(self, tr):
        """Filter trace according to config settings."""
        if tr is not None:
            tr.detrend()
            tr.filter('bandpass',
                      freqmin=self.config.fmin,
                      freqmax=self.config.fmax,
                      zerophase=True)
            if self.config.decimation_factor:
                tr.decimate(self.config.decimation_factor, no_filter=True)
            tr.data = np.array(tr.data, dtype=np.float32)

    def phase_window(self, event, station, distance):
        """
        Returns the start and end time of the template assuming
        a straight ray path and constant P wave velocity.
        """
        depth = event.origins[0].get('depth', 5e3)
        if depth == None:
            depth = 5e3
        depth /= 1e3
        dz = depth + station.elevation / 1e3
        path_length = np.sqrt(dz**2 + distance**2)

        p_time = 2 + path_length / 8.
        start = event.origins[0].time + p_time - self.config.prepick

        if self.config.length_fixed:
            return [start, start + self.config.min_length]

        s_time = 8 + p_time * 1.5
        end = event.origins[0].time + s_time + self.config.min_win_len
        # rescale to ensure discrete 5 second increments in window length
        length = 5 * (end - start) // 5 + 5
        return [start, start + length]

    def construct_data_path(self, net, sta, loc, cha, year, julday,
                            quality, path_attr='data_path',
                            structure_attr='data_structure'):
        """Return the path to the data file."""
        if isinstance(julday, int):
            # enforce 3 digit integer
            julday = f'{julday:03}'

        data_path = getattr(self.config, path_attr)
        data_structure = getattr(self.config, structure_attr)

        return data_structure.format(
                    data_path=data_path,
                    net=net,
                    sta=sta,
                    loc=loc,
                    cha=cha,
                    year=year,
                    julday=julday,
                    quality=quality
                    )


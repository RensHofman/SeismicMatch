# -*- coding: utf-8 -*-
"""Module containing the template matching TM class."""
import sys
import os
import traceback
from glob import glob
import logging
from timeit import default_timer as timer

import numpy as np
from scipy.fftpack import next_fast_len
from obspy import read
from obspy.signal.cross_correlation import correlate
from obspy.signal.cross_correlation import xcorr_max
from obspy import UTCDateTime
from obspy.io.mseed.util import get_record_information

logger = logging.getLogger(__name__)

# Fallback to numpy if cupy is not available
cp = np

class TemplateMatcher:

    def __init__(self, config, data_handler, pool):
        """Initiate the template matcher."""
        self.config = config

        if self.config.use_cupy:
            global cp
            import cupy as _cp
            cp = _cp

        self.dh = data_handler
        self.pool = pool

    def set_cuda_device(self, cuda_device):
        """Set the CUDA device for GPU computation."""
        cp.cuda.Device(cuda_device).use()

    def sampling_rate(self, fname):
        """Return the sampling rate of the waveform file."""
        stats = get_record_information(fname)
        return stats['samp_rate']

    def estimate_gpu_capacity(self, sample_rate):
        """If a GPU is used, estimate the maximum number of data traces."""
        if not self.config.use_cupy:
            return 30
        logger.debug("Testing GPU memory capacity.")
        # number of samples in full data trace
        n_samples = int(sample_rate * 86400)
        # resulting cross-correlation length
        cc_len = next_fast_len(n_samples)
        N_MAX = 1
        while True:
            try:
                # try to allocate memory for all cross-correlations
                cc = cp.empty((cc_len, N_MAX, N_MAX), dtype=cp.complex64)
            except cp.cuda.memory.OutOfMemoryError:
                break
            N_MAX += 1
        logger.debug(f"Succesfully allocated memory for {N_MAX - 1} traces.")
        return N_MAX - 1

    def find_optimal_chunksize(self, chunk, N):
        """Optimal size for matrix cc.

        Return a chunksize below chunk that is closest to an
        integer division of N.
        """
        # number of iterations needed
        n_it = int(N / chunk) + (N % chunk > 0)
        # optimal chunk size without increasing n_it
        chunk = int(N / n_it) + (N % n_it > 0)
        return chunk

    def match_templates(self, all_templates):
        """Match the given templates against corresponding continuous data."""
        waveform_id = all_templates[0].split('_')[0]
        all_templates = np.array([f'{self.config.template_dir}/{temp}'
                                      for temp in all_templates])
        all_data = self.dh.prepare_data_list(waveform_id,
                                             self.config.data_start,
                                             self.config.data_stop)
        sample_rate = self.sampling_rate(all_templates[0])
        n_data, n_templates = len(all_data), len(all_templates)

        if not all_data:
            logger.info(f"No data found for channel {waveform_id}.")
            return

        n_cc = n_data * n_templates

        # break calculation in parts that fit on GPU memory
        N_MAX = self.estimate_gpu_capacity(sample_rate)
        if n_templates < N_MAX:
            N_MAX = int(N_MAX**2 / n_templates / 2)
        # find lowest N_MAX that does not increase the number of iterations
        N_MAX = self.find_optimal_chunksize(N_MAX, n_data)

        # data and template pointers
        di, ti = 0, 0
        data, templates = [], []
        n_detections = 0
        cc_len = 0

        timer_start = timer()
        while True:
            try:
                cc_timer = timer()
                # load data streams on GPU if selection changed
                if data != all_data[di:di+N_MAX]:
                    data = all_data[di:di+N_MAX]
                    data_st, t_data = self.dh.read_bulk_data(
                                            data, pool=self.pool,
                                            bandpass=True)
                    if data_st is not None:
                        data_len = [len(tr) for tr in data_st]
                        _cc_len = next_fast_len(max(data_len))
                        # temps need to be reloaded when cc_len changes
                        if _cc_len != cc_len:
                            cc_len = _cc_len
                            templates = []
                        # calculate fft
                        data_fft = cp.zeros((len(data_st), cc_len),
                                            dtype=cp.complex64)
                        for i, tr in enumerate(data_st):
                            data_fft[i,] = cp.fft.fft(tr, n=cc_len)

                if data_st is not None:
                    # load templates on GPU if selection changed
                    if len(templates) == 0 or templates[0] != all_templates[ti]:
                        templates = all_templates[ti:ti+N_MAX]
                        temp_st, t_temp = self.dh.read_bulk_data(
                                                templates,
                                                pool=self.pool,
                                                method='make_equal_length',
                                                bandpass=False)
                        st_len, _ = temp_st.shape
                        # calculate fft
                        temp_fft = cp.zeros((st_len, cc_len),
                                            dtype=cp.complex64)
                        for i, tr in enumerate(temp_st):
                            temp_fft[i,] = cp.fft.fft(tr.conj(),
                                                      n=cc_len)[::-1]

                    # perform cross-correlations
                    n = self.matrix_cc(temp_st, data_st, temp_fft,
                                       data_fft, templates, t_data)
                    n_detections += n
                    t_cc = timer() - cc_timer
                    _n_cc = len(data)*len(templates)
                    logger.debug(f"processed {_n_cc} cross-correlations "
                                 f"at {_n_cc/t_cc:.2f} /s")
                    sys.stdout.flush()

                # if no exception has occurred, cleanup data and increment
                ti += N_MAX
                # if all templates processed
                if ti >= n_templates:
                    # increment data pointer
                    di += N_MAX
                    # stop if all data is processed
                    if di >= n_data:
                        break
                    # reset template pointer
                    ti = 0
                    try:
                        del data_st, data_fft
                    except:
                        pass
                else:
                    try:
                        del temp_st, temp_fft
                    except:
                        pass

            # restart iteration with less data in case of memory problem
            except Exception as e:
                if (self.config.use_cupy and
                        isinstance(e, cp.cuda.memory.OutOfMemoryError)):
                    N_MAX -= 1
                    N_MAX = self.find_optimal_chunksize(
                                    N_MAX,
                                    len(all_data) - di
                                    )
                    logger.debug("GPU memory full, reducing "
                                 f"chunk size to {N_MAX}")
                    if N_MAX == 0:
                        logger.error("No free memory on GPU.")
                        sys.exit(1)
                    try:
                        data, templates = [], []
                        del data_st
                        del temp_st
                    except NameError:
                        pass
                else:
                    raise
            except Exception:
                logger.error("Unexpected error:")
                raise

        cc_time = timer() - timer_start
        logger.debug(f"processed {n_cc} cross correlations at an average "
                     f"rate of {n_cc/cc_time:.2f} /s")
        logger.debug(f"Found {n_detections} new detection(s)")
        return

    def find_peaks(self, day_cc, distance):
        """Find peaks in the cc result.

        Return a list of sample indices where the cross
        correlations exceed the threshold value, followed
        by a list of cc values and mad values.
        """
        abs_cc = cp.abs(day_cc)
        cc_len = len(day_cc)
        # calculate daily MAD
        median = cp.median(day_cc)
        mad = cp.median(cp.abs(day_cc - median))
        # water level
        if mad == 0:
            mad = 1e-6
        # define local threshold
        if self.config.combine_thresholds:
            local_threshold = max([self.config.cc_threshold,
                                   self.config.mad_threshold * mad])
        else:
            local_threshold = min([self.config.cc_threshold,
                                   self.config.mad_threshold * mad])
        tops = cp.where(abs_cc >= local_threshold)[0]
        peaks = cp.zeros(cc_len, dtype=bool)
        # iterate over all values above threshold
        it = iter(tops)
        for x in it:
            if float(abs_cc[x]) < local_threshold:
                break
            p = float(abs_cc[x])
            peaks[x] = True
            # while the cc remains above threshold, overwrite
            # maximum value and index
            while x + 1 < cc_len:
                if float(abs_cc[x + 1]) < local_threshold:
                    break
                if float(abs_cc[x + 1]) > p:
                    p = float(abs_cc[x + 1])
                    peaks[x] = False
                    peaks[x + 1] = True
                x += 1
                try:
                    next(it)
                except:
                    break
        tops = cp.where(peaks)[0]
        # all daily matches, sorted by CC high to low
        for x in sorted(tops, key=lambda x: abs_cc[x], reverse=True):
            if not peaks[x]:
                continue
            # ignore peaks that are too close to current peak
            peaks[x-distance:x+distance] = False
            peaks[x] = True
        tops = cp.where(peaks)[0]
        cc_values = day_cc[tops]
        mad_values = cc_values / mad
        return tops, cc_values, mad_values

    def process_matches(self, peaks, cc, mad, amps, data_start, template_file):
        """Find and process matches in the cross-correlation."""
        template_st = read(template_file, headonly=True)
        temp_id = template_file.split('/')[-1]
        sample_rate = template_st[0].stats.sampling_rate

        new_detections = 0
        with open(f'{self.config.matches_dir}/{temp_id}', 'a+') as f:
            for x, cc_c, x_mad, amp in zip(peaks, cc, mad, amps):
                time = data_start + float(x) / sample_rate
                new_detections += 1
                f.write((f"{time.format_fissures()} "
                         f"{cc_c:.3f} {x_mad:.3f} {amp:.3E}\n"))
        return new_detections

    def matrix_cc(self, templates, data, temp_fft,
                  data_fft, temp_files, t_data):
        """Compute cross-correlations.

        Perform cross correlations of all data and
        all templates and process result immediately.
        """
        n_templates, N = templates.shape
        n_data = len(data)
        data_len = [len(tr) for tr in data]
        cc_len = next_fast_len(max(data_len))

        if N > cc_len:
            print('data traces must be longer than templates')
            return 0

        # cross-correlation
        cc_matrix = cp.einsum('ik,jk->ijk',
                              temp_fft,
                              data_fft,
                              dtype=np.complex64)

        # normalize and process results
        n_matches = 0
        for j, data_tr in enumerate(data):
            M = data_len[j]
            if M < N:
                continue
            pad = 1
            pad1, pad2 = (pad + 1) // 2, pad // 2
            padded_tr = self.pad_zeros(data_tr, M, pad1, pad2)
            data_abs = cp.abs(data_tr)
            data_norm = self.window_sum(padded_tr ** 2, N)

            for i, temp_tr in enumerate(templates):
                cc = cp.fft.ifft(cc_matrix[i, j,])[:M-N+1]
                cc = cp.real(cc)
                norm = data_norm * cp.sum(temp_tr ** 2)
                norm = cp.sqrt(norm)
                temp_amp = cp.max(cp.abs(temp_tr))
                mask = data_norm <= (cp.finfo(norm.dtype).eps * N) ** .5

                if cc.dtype == float:
                    cc[~mask] /= norm[~mask]
                else:
                    cc /= norm
                    cc[mask] = 0

                # when data is corrupt CC explodes ...
                mask = cp.abs(cc) > 1.01
                if cp.any(mask):
                    print('Warning: cc > 1.0')
                    sys.stdout.flush()
                    cc[mask] = 0
                # process results
                peaks, cc_vals, mad_vals = self.find_peaks(cc, N)
                if len(peaks) == 0:
                    continue
                amp_ratios = [cp.max(data_abs[idx:idx+N])/temp_amp
                              for idx in peaks]
                n_matches += self.process_matches(
                                 peaks, cc_vals, mad_vals, amp_ratios,
                                 t_data[j], temp_files[i])
        del cc_matrix
        return n_matches

    def window_sum(self, data, window_len):
        """Return the rolling sum of data."""
        window_sum = cp.convolve(data, cp.ones(window_len,
                                               dtype=cp.int16), 'valid')
        return window_sum[1:]

    def pad_zeros(self, a, M, num, num2=None):
        """Pad num zeros at both sides of array a."""
        if num2 is None:
            num2 = num
        padded = cp.zeros(M + num + num2, dtype=a.dtype)
        if num2:
            padded[num:-num2] = a
            return padded
        padded[num:] = a
        return padded

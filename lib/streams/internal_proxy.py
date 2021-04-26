"""
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the “Software”), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

import datetime
import errno
import re
import requests
import time

from collections import OrderedDict

import lib.m3u8 as m3u8
from lib.tvheadend.atsc import ATSCMsg
from lib.tvheadend.templates import tvh_templates
from .stream import Stream


class InternalProxy(Stream):

    def __init__(self, _plugins, _hdhr_queue):
        self.last_refresh = None
        super().__init__(_plugins, _hdhr_queue)

    def gen_response(self, _ch_num, _tuner):
        """
        Returns dict where the dict is consistent with
        the method do_dict_response requires as an argument
        A code other than 200 means do not tune
        dict also include a "tuner_index" that informs caller what tuner is allocated
        """
        index = self.find_tuner(_ch_num, _tuner)
        if index >= 0:
            return {
                'tuner': index,
                'code': 200,
                'headers': {'Content-type': 'video/mp2t; Transfer-Encoding: chunked codecs="avc1.4D401E'},
                'text': None}
        else:
            self.logger.warning('All tuners already in use')
            return {
                'tuner': index,
                'code': 400,
                'headers': {'Content-type': 'text/html'},
                'text': tvh_templates['htmlError'].format('400 - All tuners already in use.')}

    def stream_direct(self, _channel_dict, _write_buffer):
        """
        Processes m3u8 interface without using ffmpeg
        """
        duration = 6
        play_queue = OrderedDict()
        file_filter = None
        self.last_refresh = time.time()
        stream_uri = self.get_stream_uri(_channel_dict)
        if not stream_uri:
            self.logger.warning('Unknown Channel')
            return
        self.logger.debug('M3U8: {}'.format(stream_uri))
        stream_filter = self.plugins.config_obj.data[_channel_dict['namespace'].lower()]['player-stream_filter']
        if stream_filter is not None:
            file_filter = re.compile(stream_filter)
        while True:
            try:
                added = 0
                removed = 0
                playlist = m3u8.load(stream_uri)
                removed += self.remove_from_stream_queue(playlist, play_queue)
                added += self.add_to_stream_queue(playlist, play_queue, file_filter)
                if added == 0 and duration > 0:
                    time.sleep(duration * 0.3)
                elif self.plugins.plugins[_channel_dict['namespace']].plugin_obj \
                        .is_time_to_refresh(self.last_refresh):
                    stream_uri = self.get_stream_uri(_channel_dict)
                    self.logger.debug('M3U8: {}'.format(stream_uri))
                    self.last_refresh = time.time()
                duration = self.play_queue(play_queue, _channel_dict, _write_buffer, duration)
            except IOError as e:
                # Check we hit a broken pipe when trying to write back to the client
                if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                    # Normal process.  Client request end of stream
                    self.logger.info('2. Connection dropped by end device {}'.format(e))
                    break
                else:
                    self.logger.error('{}{}'.format(
                        '3 UNEXPECTED EXCEPTION=', e))
                    raise

    def add_to_stream_queue(self, _playlist, _play_queue, _file_filter):
        total_added = 0
        for m3u8_segment in _playlist.segments:
            uri = m3u8_segment.absolute_uri
            if uri not in _play_queue:
                played = False
                if _file_filter is not None:
                    m = _file_filter.match(uri)
                    if m:
                        played = True
                _play_queue[uri] = {
                    'played': played,
                    'duration': m3u8_segment.duration
                }
                self.logger.debug(f"Added {uri} to play queue")
                total_added += 1
        return total_added

    def remove_from_stream_queue(self, _playlist, _play_queue):
        total_removed = 0
        for segment_key in list(_play_queue.keys()):
            is_found = False
            for segment_m3u8 in _playlist.segments:
                uri = segment_m3u8.absolute_uri
                if segment_key == uri:
                    is_found = True
                    break
            if not is_found:
                del _play_queue[segment_key]
                total_removed += 1
                self.logger.debug(f"Removed {segment_key} from play queue")
                continue
            else:
                break
        return total_removed

    def play_queue(self, _play_queue, _channel_dict, _write_buffer, _duration):
        for uri, data in _play_queue.items():
            if not data["played"]:
                start_download = datetime.datetime.utcnow()
                chunk = requests.get(uri).content
                data['played'] = True
                if not chunk:
                    self.logger.warning(f"Segment {uri} not available. Skipping..")
                    continue
                atsc_msg = ATSCMsg()
                chunk_updated = atsc_msg.update_sdt_names(chunk[:80], _channel_dict['namespace'].encode(),
                    self.set_service_name(_channel_dict).encode())
                chunk = chunk_updated + chunk[80:]
                _duration = data['duration']
                runtime = (datetime.datetime.utcnow() - start_download).total_seconds()
                target_diff = 0.3 * _duration
                wait = target_diff - runtime
                self.logger.info(f"Serving {uri} ({_duration}s)")
                _write_buffer.write(chunk)
                if wait > 0:
                    time.sleep(wait)
        return _duration
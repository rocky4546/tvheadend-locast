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

import errno
import json
import subprocess
import time

from lib.tvheadend.templates import tvh_templates
from .stream import Stream
from .stream_queue import StreamQueue
from .pts_validation import PTSValidation
from lib.db.db_config_defn import DBConfigDefn


MIN_TIME_BETWEEN_LOCAST = 0.9


class FFMpegProxy(Stream):

    def __init__(self, _plugins, _hdhr_queue):
        self.ffmpeg_proc = None
        self.last_refresh = None
        self.block_prev_time = None
        self.buffer_prev_time = None
        self.small_pkt_streaming = False
        self.block_max_pts = 0
        self.block_prev_pts = 0
        self.prev_last_pts = 0
        self.default_duration = 0
        self.block_moving_avg = 0
        self.channel_dict = None
        self.write_buffer = None
        self.stream_queue = None
        self.pts_validation = None
        super().__init__(_plugins, _hdhr_queue)
        self.config = self.plugins.config_obj.data
        self.db_configdefn = DBConfigDefn(self.config)


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

    def stream_ffmpeg(self, _channel_dict, _write_buffer):
        self.channel_dict = _channel_dict
        self.write_buffer = _write_buffer
        self.config = self.db_configdefn.get_config()
        self.pts_validation = PTSValidation(self.config, self.channel_dict)
        channel_uri = self.get_stream_uri(self.channel_dict)
        if not channel_uri:
            self.logger.warning('Unknown Channel')
            return
        self.ffmpeg_proc = self.open_ffmpeg_proc(channel_uri)
        time.sleep(0.01)
        self.last_refresh = time.time()
        self.block_prev_time = self.last_refresh
        self.buffer_prev_time = self.last_refresh
        video_data = self.read_buffer()
        while True:
            if not video_data:
                self.logger.debug('No Video Data, refreshing stream')
                self.ffmpeg_proc = self.refresh_stream()
            else:
                try:
                    if self.config['locast']['is_free_account']:
                        video_data = self.validate_stream(video_data)
                    self.write_buffer.write(video_data)
                except IOError as e:
                    if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                        self.logger.info('1. Connection dropped by end device')
                        break
                    else:
                        self.logger.error('{}{}'.format(
                            '1 ################ UNEXPECTED EXCEPTION=', e))
                        raise
            try:
                video_data = self.read_buffer()
            except Exception as e:
                self.logger.error('{}{}'.format(
                    '2 ################ UNEXPECTED EXCEPTION=', e))
                raise
        self.logger.debug('Terminating ffmpeg stream')
        self.ffmpeg_proc.terminate()
        try:
            self.ffmpeg_proc.communicate()
        except ValueError:
            pass

    def validate_stream(self, video_data):
        if not self.config[self.channel_dict['namespace'].lower()]['player-enable_pts_filter']:
            return video_data
            
        has_changed = True
        while has_changed:
            has_changed = False
            results = self.pts_validation.check_pts(video_data)
            if results['byteoffset'] != 0:
                if results['byteoffset'] < 0:
                    self.write_buffer.write(video_data[-results['byteoffset']:len(video_data) - 1])
                else:
                    self.write_buffer.write(video_data[0:results['byteoffset']])
                has_changed = True
            if results['refresh_stream']:
                self.ffmpeg_proc = self.refresh_stream()
                video_data = self.read_buffer()
                has_changed = True
            if results['reread_buffer']:
                video_data = self.read_buffer()
                has_changed = True
        return video_data

    def read_buffer(self):
        data_found = False
        video_data = None
        idle_timer = 2
        while not data_found:
            video_data = self.stream_queue.read()
            if video_data:
                data_found = True
            else:
                time.sleep(0.2)
                idle_timer -= 1
                if idle_timer == 0:
                    if self.plugins.plugins[self.channel_dict['namespace']].plugin_obj \
                            .is_time_to_refresh(self.last_refresh):
                        self.ffmpeg_proc = self.refresh_stream()
        # with open("x.ts"+str(datetime.datetime.now().timestamp()), 'wb') as temp_file:
        # with open("x.ts", 'wb') as temp_file:
        #   temp_file.write(video_data)
        return video_data

    def refresh_stream(self):
        self.last_refresh = time.time()
        channel_uri = self.get_stream_uri(self.channel_dict)
        try:
            self.ffmpeg_proc.terminate()
            self.ffmpeg_proc.wait(timeout=0.1)
            self.logger.debug('Previous ffmpeg terminated')
        except ValueError:
            pass
        except subprocess.TimeoutExpired:
            # try one more time.  If the process does not terminate
            # a socket error will occur with locast having 2 connections.
            self.ffmpeg_proc.terminate()
            time.sleep(0.01)

        self.logger.debug('{}{}'.format(
            'Refresh Stream channelUri=', channel_uri))
        ffmpeg_process = self.open_ffmpeg_proc(channel_uri)
        # make sure the previous ffmpeg is terminated before exiting        
        self.buffer_prev_time = time.time()
        return ffmpeg_process

    def open_ffmpeg_proc(self, _channel_uri):
        """
        ffmpeg drops the first 9 frame/video packets when the program starts.
        this means everytime a refresh occurs, 9 frames will be dropped.  This is
        visible by looking at the video packets for a 6 second window being 171
        instead of 180.  Following the first read, the packets increase to 180.
        """
        ffmpeg_command = [self.config['paths']['ffmpeg_path'],
            '-i', str(_channel_uri),
            '-f', 'mpegts',
            '-nostats',
            '-hide_banner',
            '-loglevel', 'warning',
            '-copyts',
            'pipe:1']
        ffmpeg_process = subprocess.Popen(ffmpeg_command,
            stdout=subprocess.PIPE,
            bufsize=-1)
        self.stream_queue = StreamQueue(188, ffmpeg_process, self.channel_dict['uid'])
        time.sleep(0.1)
        return ffmpeg_process

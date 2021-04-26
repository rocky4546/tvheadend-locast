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

import os
import subprocess
import errno
import urllib
import pathlib
import logging
import time
import socket
import json
from threading import Thread
from logging import config
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import lib.tvheadend.utils as utils
from lib.tvheadend.templates import tvh_templates
from lib.config.config_defn import ConfigDefn
from lib.db.db_plugins import DBPlugins
from lib.db.db_channels import DBChannels
from lib.streams.m3u8_redirect import M3U8Redirect
from lib.streams.internal_proxy import InternalProxy
from lib.streams.ffmpeg_proxy import FFMpegProxy

MIN_TIME_BETWEEN_LOCAST = 0.4


class TunerHttpHandler(BaseHTTPRequestHandler):
    # class variables
    plugins = None
    namespace_list = None
    hdhr_queue = None
    config = None
    rmg_station_scans = []
    logger = None
    channels_db = None
    m3u8_redirect = None
    internal_proxy = None

    def __init__(self, *args):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
        self.ffmpeg_proc = None  # process for running ffmpeg
        self.block_moving_avg = 0
        self.bytes_per_read = 0
        self.last_refresh = None
        self.block_prev_pts = 0
        self.block_prev_time = None
        self.buffer_prev_time = None
        self.block_max_pts = 0
        self.small_pkt_streaming = False
        self.real_namespace = None
        self.real_instance = None
        super().__init__(*args)

    def log_message(self, _format, *args):
        self.logger.debug('[%s] %s' % (self.address_string(), _format % args))

    def do_GET(self):
        content_path, query_data = self.get_query_data()
        if content_path.startswith('/auto/v'):
            channel = content_path.replace('/auto/v', '')
            station_list = TunerHttpHandler.channels_db.get_channels(query_data['name'], query_data['instance'])
            if channel not in station_list.keys():
                # check channel number
                for station in station_list.keys():
                    if station_list[station]['number'] == channel:
                        self.do_tuning(station, query_data['name'], query_data['instance'])
                        return
            else:
                self.do_tuning(channel, query_data['name'], query_data['instance'])
                return
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown channel'))

        elif content_path.startswith('/logreset'):
            logging.config.fileConfig(fname=self.config['paths']['config_file'], disable_existing_loggers=False)
            self.do_mime_response(200, 'text/html')

        elif content_path.startswith('/watch'):
            sid = content_path.replace('/watch/', '')
            self.do_tuning(sid, query_data['name'], query_data['instance'])
        else:
            self.logger.warning("Unknown request to " + content_path)
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Not Implemented'))
        return

    def do_POST(self):
        content_path = self.path
        query_data = {}
        self.logger.debug('Receiving a post form {}'.format(content_path))
        # get POST data
        if self.headers.get('Content-Length') != '0':
            post_data = self.rfile.read(int(self.headers.get('Content-Length'))).decode('utf-8')
            # if an input is empty, then it will remove it from the list when the dict is gen
            query_data = urllib.parse.parse_qs(post_data)

        # get QUERYSTRING
        if self.path.find('?') != -1:
            get_data = self.path[(self.path.find('?') + 1):]
            get_data_elements = get_data.split('&')
            for get_data_item in get_data_elements:
                get_data_item_split = get_data_item.split('=')
                if len(get_data_item_split) > 1:
                    query_data[get_data_item_split[0]] = get_data_item_split[1]

        self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Badly Formatted Message'))
        return

    def get_query_data(self):
        content_path = self.path
        query_data = {}
        if self.headers.get('Content-Length') is not None \
                and self.headers.get('Content-Length') != '0':
            post_data = self.rfile.read(int(self.headers.get('Content-Length'))).decode('utf-8')
            # if an input is empty, then it will remove it from the list when the dict is gen
            query_data = urllib.parse.parse_qs(post_data)

        if self.path.find('?') != -1:
            content_path = self.path[0:self.path.find('?')]
            get_data = self.path[(self.path.find('?') + 1):]
            get_data_elements = get_data.split('&')
            for get_data_item in get_data_elements:
                get_data_item_split = get_data_item.split('=')
                if len(get_data_item_split) > 1:
                    query_data[get_data_item_split[0]] = get_data_item_split[1]
        if 'name' not in query_data:
            query_data['name'] = None
        if 'instance' not in query_data:
            query_data['instance'] = None
        if query_data['instance'] or query_data['name']:
            return content_path, query_data

        path_list = content_path.split('/')
        if len(path_list) > 2:
            instance = None
            for ns in TunerHttpHandler.namespace_list:
                if path_list[1].lower() == ns.lower():
                    namespace = ns
                    del path_list[1]
                    instance_list = TunerHttpHandler.namespace_list[namespace]
                    if len(path_list) > 2:
                        for inst in instance_list:
                            if inst.lower() == path_list[1].lower():
                                instance = inst
                                del path_list[1]
                    query_data['name'] = namespace
                    query_data['instance'] = instance
                    content_path = '/'.join(path_list)
                    break
        return content_path, query_data

    def do_mime_response(self, code, mime, reply_str=None):
        self.do_dict_response({ 
            'code': code, 'headers': {'Content-type': mime},
            'text': reply_str
            })

    def do_dict_response(self, rsp_dict):
        """
        { 'code': '[code]', 'headers': { '[name]': '[value]', ... }, 'text': b'...' }
        """
        self.send_response(rsp_dict['code'])
        for header, value in rsp_dict['headers'].items():
            self.send_header(header, value)
        self.end_headers()
        if rsp_dict['text']:
            self.wfile.write(rsp_dict['text'].encode('utf-8'))

    def read_buffer(self):
        video_data = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
        return video_data

    def write_buffer(self, msg):
        self.wfile.write(msg)

    def get_stream_uri(self, sid):
        return self.plugins.plugins[self.real_namespace].plugin_obj.get_channel_uri(sid, self.real_instance)

    def do_tuning(self, sid, _namespace, _instance):
        try:
            station_list = TunerHttpHandler.channels_db.get_channels(_namespace, _instance)
            self.real_namespace = station_list[sid]['namespace']
            self.real_instance = station_list[sid]['instance']
        except KeyError:
            self.logger.warning('Unknown channel id {}'.format(sid))
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown channel'))
            return

        if self.config[self.real_namespace.lower()]['player-stream_type'] == 'm3u8redirect':
            self.do_dict_response(TunerHttpHandler.m3u8_redirect.gen_response(station_list[sid]))
            return

        elif self.config[self.real_namespace.lower()]['player-stream_type'] == 'internalproxy':
            resp = TunerHttpHandler.internal_proxy.gen_response(station_list[sid]['number'], TunerHttpHandler)
            self.do_dict_response(resp)
            if resp['tuner'] < 0:
                return
            else:
                TunerHttpHandler.internal_proxy.stream_direct(station_list[sid], self.wfile)
                
                self.logger.info('2 Locast Connection Closed')
                TunerHttpHandler.rmg_station_scans[resp['tuner']] = 'Idle'

        elif self.config[self.real_namespace.lower()]['player-stream_type'] == 'ffmpegproxy':
            resp = TunerHttpHandler.ffmpeg_proxy.gen_response(station_list[sid]['number'], TunerHttpHandler)
            self.do_dict_response(resp)
            if resp['tuner'] < 0:
                return
            else:
                self.stream_direct(sid, station_list)
                self.logger.info('1 Locast Connection Closed')
                TunerHttpHandler.rmg_station_scans[resp['tuner']] = 'Idle'
        else:
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown streamtype'))
            self.logger.error('Unknown [player-stream_type] {}'
                .format(self.config[self.real_namespace.lower()]['player-stream_type']))

    def stream_ffmpeg(self, sid, station_list):
        channel_uri = self.get_stream_uri(sid)
        if not channel_uri:
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown channel'))
            return
        self.ffmpeg_proc = self.open_ffmpeg_proc(channel_uri, station_list, sid)

        # get initial video_data. if that works, then keep grabbing it
        video_data = self.read_buffer()
        self.last_refresh = time.time()
        self.block_prev_time = time.time()
        self.buffer_prev_time = time.time()
        while True:
            if not video_data:
                self.logger.debug('No Video Data, refreshing stream')
                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                video_data = self.read_buffer()
            else:
                try:
                    if self.config[self.real_namespace.lower()]['is_free_account']:
                        video_data = self.check_pts(video_data, station_list, sid)
                    self.write_buffer(video_data)

                except IOError as e:
                    # Check we hit a broken pipe when trying to write back to the client
                    if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                        # Normal process.  Client request end of stream
                        self.logger.info('1. Connection dropped by end device')
                        break
                    else:
                        self.logger.error('{}{}'.format(
                            '1 UNEXPECTED EXCEPTION=', e))
                        raise

            try:
                video_data = self.read_buffer()
            except Exception as e:
                self.logger.error('{}{}'.format(
                    '2 UNEXPECTED EXCEPTION=', e))

        # Send SIGTERM to shutdown ffmpeg
        self.logger.debug('Terminating ffmpeg stream')
        self.ffmpeg_proc.terminate()
        try:
            # ffmpeg writes a bit of data out to stderr after it terminates,
            # need to read any hanging data to prevent a zombie process.
            self.ffmpeg_proc.communicate()
        except ValueError:
            pass

    #######
    # checks the PTS in the video stream.  If a bad PTS packet is found, 
    # it will update the video stream until the stream is valid.
    def check_pts(self, video_data, station_list, sid):
        while True:
            # check the dts in videoData to see if we should throw it away
            ffprobe_command = [self.config['paths']['ffprobe_path'],
                '-print_format', 'json',
                '-v', 'quiet', '-show_packets',
                '-select_streams', 'v:0',
                '-show_entries', 'side_data=:packet=pts,pos',
                '-']
            cmdpts = subprocess.Popen(ffprobe_command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            ptsout = cmdpts.communicate(video_data)[0]
            exit_code = cmdpts.wait()
            if exit_code != 0:
                self.logger.info('FFPROBE failed to execute with error code: {}'
                    .format(exit_code))
            pts_json = json.loads(ptsout)
            try:
                pkt_len = len(pts_json['packets'])
            except KeyError:
                pkt_len = 0
            if pkt_len < 1:
                # This occurs when the buffer size is too small, so no video packets are sent
                self.logger.debug('Packet received with no video packet included')
                break
            elif pkt_len < int(self.config[self.real_namespace.lower()]['player-min_pkt_rcvd']):
                # need to keep it from hitting bottom
                self.bytes_per_read = int(self.bytes_per_read * 1.5 / 1316) * 1316  # increase buffer size by 50%
                # self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                self.logger.debug('{} {}  {}{}'.format(
                    'MIN pkts rcvd limit, adjusting READ BUFFER to =',
                    self.bytes_per_read,
                    'Pkts Rcvd=', pkt_len))
            elif pkt_len > int(self.config[self.real_namespace.lower()]['player-max_pkt_rcvd']):
                # adjust the byte read to keep the number of packets below 100
                # do not adjust up if packets are too low.
                self.bytes_per_read = int(self.bytes_per_read
                                          * int(self.config[self.real_namespace.lower()]['player-max_pkt_rcvd']) * 0.9
                                          / pkt_len / 1316) * 1316
                # self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                self.logger.debug('{} {}  {}{}'.format(
                    'MAX pkts rcvd limit, adjusting READ BUFFER to =',
                    self.bytes_per_read,
                    'Pkts Rcvd=', pkt_len))

            try:
                first_pts = pts_json['packets'][0]['pts']
                end_of_json = len(pts_json['packets']) - 1
                last_pts = pts_json['packets'][end_of_json]['pts']
            except KeyError:
                # Since we are requesting video only packets, this should not
                # happen, but it does, so do the same as if the pkt_len < 1
                self.logger.debug('KeyError exception: no pts in first packet, ignore')
                break

            delta_pts = abs(last_pts - first_pts)
            self.logger.debug('{}{} {}{} {}{} {}{}'.format(
                'First PTS=', pts_json['packets'][0]['pts'],
                'Last PTS=', last_pts,
                'Delta=', delta_pts,
                'Pkts Rcvd=', pkt_len))
            time.sleep(0.1)
            pts_minimum = int(self.config[self.real_namespace.lower()]['player-pts_minimum'])
            if delta_pts > int(self.config[self.real_namespace.lower()]['player-pts_max_delta']) \
                    or (last_pts < pts_minimum and not self.small_pkt_streaming):
                # PTS is 90,000 per second.
                # if delta is big, then this is bad PTS
                # PTS is setup to be current time on a 24 hour clock, so 
                # the bad packets that may be good are just after midnight; otherwise
                # it is a bad packet.
                # reset stream and try again.

                # need to determine if part of the stream obtained is good 
                # and should be sent
                if first_pts < pts_minimum:
                    if last_pts < pts_minimum:
                        # entire stream is bad and has small pts for entire stream
                        # happens mostly when the stream starts or restarts
                        self.small_pkt_streaming = True
                        self.logger.info('Small PTS for entire stream, drop and refresh buffer')

                    else:
                        # RARE CASE
                        # first part of the stream is bad and
                        # end part of the stream is good
                        self.logger.info('Small PTS for with large PTS on end, drop and refresh buffer')
                elif last_pts < pts_minimum:
                    # RARE CASE
                    # first part of the stream is good
                    # but last part is a small pts
                    byte_offset = self.find_bad_pkt_offset(pts_json)
                    if byte_offset > 0:
                        self.write_buffer(video_data[0:byte_offset])
                        self.logger.info('{} {} {} {}'.format(
                            'Good PTS on front with small PTS on end.',
                            'Writing good bytes=', byte_offset,
                            'out to client and refreshing buffer'))
                    else:
                        self.logger.info('Small PTS unknown case, drop and refreshing buffer')

                else:
                    # MAIN CASE
                    # both pts are large, but delta is also too big
                    # Standard case which can occur every 15 minutes
                    byte_offset = self.find_bad_pkt_offset(pts_json)
                    if byte_offset > 0:  # if -1, then offset was not found, drop everything
                        self.write_buffer(video_data[0:byte_offset])
                        self.logger.info('{} {}{} {}'.format(
                            'Large delta PTS with good front.',
                            'Writing good bytes=', byte_offset,
                            'out to client and double refreshing buffer'))
                    else:
                        self.logger.info('Large delta but no bad PTS ... unknown case, ignore')
                        break

                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                self.block_prev_time = time.time()
                # videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                video_data = self.read_buffer()
                self.logger.debug('Stream reset')
            else:
                # valid video stream found
                if last_pts >= pts_minimum:
                    self.small_pkt_streaming = False

                # need to save time and determine if the delta from the last time was over x seconds
                # if it was, need to print out the PTS delta and reset the data.
                if self.block_prev_pts > 0 and time.time() - self.buffer_prev_time > MIN_TIME_BETWEEN_LOCAST:
                    # pkts are normally 3000-6000 pts apart for 720 broadcast and 9000-12000 for 480
                    if first_pts < self.block_max_pts - 20000:
                        # some packets are in the past
                        if last_pts < self.block_max_pts:
                            # all packets are in the past, drop and reload
                            self.logger.info('Entire PTS buffer in the past last_pts={} vs max={}'.format(last_pts,
                                self.block_max_pts))
                            video_data = self.read_buffer()
                        else:
                            # a potion of the packets are in the past.
                            # find the point and then write the end of the buffer to the stream
                            byte_offset = self.find_past_pkt_offset(pts_json, self.block_max_pts)
                            self.logger.info('{} {}{} {}'.format(
                                'PTS buffer in the past.',
                                ' Writing end bytes from offset=', byte_offset,
                                'out to client'))
                            if byte_offset < 0:
                                # means entire buffer is in the past. skip
                                pass
                            else:
                                # write end of buffer from byte_offset
                                self.write_buffer(video_data[byte_offset:len(video_data) - 1])
                            video_data = self.read_buffer()
                    else:

                        block_delta_time = time.time() - self.block_prev_time
                        self.buffer_prev_time = time.time()
                        block_pts_delta = first_pts - self.block_prev_pts
                        self.block_prev_time = time.time()
                        self.block_prev_pts = first_pts
                        # calculate a running average
                        if self.block_moving_avg == 0:
                            self.block_prev_pts = first_pts
                            self.block_moving_avg = 10 * block_pts_delta  # 10 point moving average
                        self.block_moving_avg = self.block_moving_avg / 10 * 9 + block_pts_delta
                        self.logger.debug('BLOCK PTS moving average = {}   BLOCK DELTA time = {}'.format(
                            int(self.block_moving_avg / 10), block_delta_time)

                        )
                        if last_pts > self.block_max_pts:
                            self.block_max_pts = last_pts
                        break
                else:
                    if self.block_prev_pts == 0:
                        self.block_prev_pts = first_pts
                        self.block_max_pts = last_pts
                    # determine how much pts has occurred since the last reset
                    block_pts_delta = last_pts - self.block_prev_pts
                    self.buffer_prev_time = time.time()

                    # determine if the pts is in the past
                    if last_pts < self.block_max_pts - 50000:
                        self.logger.info('PTS in the past {} vs max={}'.format(last_pts, self.block_max_pts))
                        # need to read the next buffer and loop around
                        video_data = self.read_buffer()

                    # determine if we are at the end of a block AND the refresh timeout has occurred.
                    elif block_pts_delta > self.block_moving_avg / 10:
                        if self.is_time_to_refresh():
                            # write out whatever we have a refresh the stream
                            if last_pts > self.block_max_pts:
                                self.block_max_pts = last_pts
                            self.write_buffer(video_data)
                            self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                            video_data = self.read_buffer()
                            # loop back around and verify the videoData is good
                        else:
                            if last_pts > self.block_max_pts:
                                self.block_max_pts = last_pts
                            break
                    else:
                        if last_pts > self.block_max_pts:
                            self.block_max_pts = last_pts
                        break
        return video_data

    def find_bad_pkt_offset(self, pts_json):
        num_of_pkts = len(pts_json['packets']) - 1  # index from 0 to len - 1
        i = 1
        prev_pkt_dts = pts_json['packets'][0]['pts']
        byte_offset = -1
        while i < num_of_pkts:
            next_pkt_pts = pts_json['packets'][i]['pts']
            if abs(next_pkt_pts - prev_pkt_dts) \
                    > int(self.config[self.real_namespace.lower()]['player-pts_max_delta']):
                # found place where bad packets start
                # only video codecs have byte position info
                byte_offset = int(int(pts_json['packets'][i]['pos']) / 1316) * 1316
                self.logger.debug('{}{}'.format('Bad PTS at byte_offset=', prev_pkt_dts))
                break

            i += 1
            prev_pkt_dts = next_pkt_pts
        return byte_offset

    def find_past_pkt_offset(self, pts_json, block_max_pts):
        num_of_pkts = len(pts_json['packets']) - 1  # index from 0 to len - 1
        next_pkt_pts = 0
        i = 0
        byte_offset = -1
        while i < num_of_pkts:
            prev_pkt_dts = next_pkt_pts
            next_pkt_pts = pts_json['packets'][i]['pts']
            if next_pkt_pts >= block_max_pts - 6000:  # at 720, a pkt is 3000-6000 in size.  Need to back up one pkt.
                # found place where future packets start
                # only video codecs have byte position info
                byte_offset = int(int(pts_json['packets'][i]['pos']) / 1316) * 1316
                self.logger.debug(
                    '{}{} {}{} {}{}'.format('Future PTS at byte_offset=', byte_offset, 'pkt_pts=', next_pkt_pts,
                        'prev_pkt=', prev_pkt_dts))
                break

            i += 1
        return byte_offset

    def is_time_to_refresh(self):
        if self.config[self.real_namespace.lower()]['is_free_account']:
            delta_time = time.time() - self.last_refresh
            refresh_rate = int(self.config[self.real_namespace.lower()]['player-refresh_rate'])
            if refresh_rate > 0 and delta_time > int(self.config[self.real_namespace.lower()]['player-refresh_rate']):
                self.logger.info('Refresh time expired. Refresh rate is {} seconds'
                    .format(self.config[self.real_namespace.lower()]['player-refresh_rate']))
                return True
        return False

    #######
    # called when the refresh timeout occurs and the stream m3u8 file is updated
    def refresh_stream(self, sid, station_list):

        self.last_refresh = time.time()
        channel_uri = self.get_stream_uri(sid)
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
            time.sleep(0.1)

        self.logger.debug('{}{}'.format(
            'Refresh Stream channelUri=', channel_uri))
        ffmpeg_process = self.open_ffmpeg_proc(channel_uri, station_list, sid)
        # make sure the previous ffmpeg is terminated before exiting        
        self.buffer_prev_time = time.time()
        return ffmpeg_process

    #######
    # returns the service name used to sync with the EPG channel name
    def set_service_name(self, station_list, sid):
        prefix = self.config[self.real_namespace.lower()]['epg-prefix']
        suffix = self.config[self.real_namespace.lower()]['epg-suffix']
        if prefix is None:
            prefix = ""
        if suffix is None:
            suffix = ""

        service_name = prefix + \
            str(station_list[sid]['number']) + \
            suffix + \
            ' ' + station_list[sid]['display_name']
        return service_name

    def open_ffmpeg_proc(self, channel_uri, station_list, sid):
        ffmpeg_command = [self.config['paths']['ffmpeg_path'],
            '-i', str(channel_uri),
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-f', 'mpegts',
            '-nostats',
            '-hide_banner',
            '-loglevel', 'warning',
            '-metadata', 'service_provider=Locast',
            '-metadata', 'service_name={}'.format(self.set_service_name(station_list, sid)),
            '-copyts',
            'pipe:1']
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
        return ffmpeg_process


class TunerHttpServer(Thread):

    def __init__(self, server_socket, _plugins):
        Thread.__init__(self)
        self.bind_ip = _plugins.config_obj.data['web']['bind_ip']
        self.bind_port = _plugins.config_obj.data['web']['plex_accessible_port']
        self.socket = server_socket
        self.start()

    def run(self):
        HttpHandlerClass = FactoryTunerHttpHandler()
        httpd = HTTPServer((self.bind_ip, int(self.bind_port)), HttpHandlerClass, bind_and_activate=False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None
        httpd.serve_forever()


def FactoryTunerHttpHandler():
    class CustomHttpHandler(TunerHttpHandler):
        def __init__(self, *args, **kwargs):
            super(CustomHttpHandler, self).__init__(*args, **kwargs)
    return CustomHttpHandler


def init_class_var(_plugins, _hdhr_queue):
    TunerHttpHandler.logger = logging.getLogger(__name__)
    TunerHttpHandler.plugins = _plugins
    TunerHttpHandler.config = _plugins.config_obj.data
    TunerHttpHandler.hdhr_queue = _hdhr_queue

    if not _plugins.config_obj.defn_json:
        _plugins.config_obj.defn_json = ConfigDefn(_config=_plugins.config_obj.data)

    plugins_db = DBPlugins(_plugins.config_obj.data)
    TunerHttpHandler.namespace_list = plugins_db.get_instances()
    TunerHttpHandler.channels_db = DBChannels(_plugins.config_obj.data)
    TunerHttpHandler.m3u8_redirect = M3U8Redirect(_plugins, _hdhr_queue)
    TunerHttpHandler.internal_proxy = InternalProxy(_plugins, _hdhr_queue)
    TunerHttpHandler.ffmpeg_proxy = FFMpegProxy(_plugins, _hdhr_queue)

    tmp_rmg_scans = []
    for x in range(int(_plugins.config_obj.data['locast']['player-tuner_count'])):
        tmp_rmg_scans.append('Idle')
    TunerHttpHandler.rmg_station_scans = tmp_rmg_scans


def start(_plugins, _hdhr_queue):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(
        (_plugins.config_obj.data['web']['bind_ip'],
        int(_plugins.config_obj.data['web']['plex_accessible_port'])))
    server_socket.listen(int(_plugins.config_obj.data['web']['concurrent_listeners']))
    utils.logging_setup(_plugins.config_obj.data['paths']['config_file'])
    logger = logging.getLogger(__name__)
    logger.debug(
        'Now listening for requests. Number of listeners={}'
            .format(_plugins.config_obj.data['web']['concurrent_listeners']))
    logger.info('Available tuners={}'.format(_plugins.config_obj.data['locast']['player-tuner_count']))
    init_class_var(_plugins, _hdhr_queue)
    for i in range(int(_plugins.config_obj.data['web']['concurrent_listeners'])):
        TunerHttpServer(server_socket, _plugins)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass

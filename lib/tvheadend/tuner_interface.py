import datetime
import os
import subprocess
import errno
import urllib
import copy
import pathlib
import logging
import requests
import time
from threading import Thread
import socket
import re
import json
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from collections import OrderedDict

import lib.m3u8 as m3u8
import lib.tvheadend.stations as stations
from lib.templates import templates
import lib.tvheadend.utils as utils
from lib.tvheadend.user_config import TVHUserConfig

MIN_TIME_BETWEEN_LOCAST = 0.4


class TunerHttpHandler(BaseHTTPRequestHandler):
    # class variables
    station_obj = None
    locast = None
    location = None
    hdhr_queue = None
    config = None
    rmg_station_scans = []
    local_locast = None

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
        self.logger = logging.getLogger(__name__)
        super().__init__(*args)

    def do_GET(self):
        base_url = self.config['main']['plex_accessible_ip'] + ':' + self.config['main']['plex_accessible_port']
        content_path = self.path

        if content_path.startswith('/auto/v'):
            channel = content_path.replace('/auto/v', '')
            if '.' in channel:
                station_list = TunerHttpHandler.station_obj.get_dma_stations_and_channels()
                for station in station_list:
                    if station_list[station]['channel'] == channel:
                        self.do_tuning(station)
                        return
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))
            else:
                self.do_tuning(channel)

        elif content_path.startswith('/watch'):
            sid = content_path.replace('/watch/', '')
            self.do_tuning(sid)
        else:
            self.logger.warning("Unknown request to " + content_path)
            self.do_response(501, 'text/html', templates['htmlError'].format('501 - Not Implemented'))
        return

    def do_POST(self):
        content_path = self.path
        query_data = {}
        self.logger.debug('receiving a post form {}'.format(content_path))
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

        self.do_response(501, 'text/html', templates['htmlError'].format('501 - Badly Formatted Message'))
        return

    def do_response(self, code, mime, reply_str=None):
        self.send_response(code)
        self.send_header('Content-type', mime)
        self.end_headers()
        if reply_str:
            self.wfile.write(reply_str.encode('utf-8'))

    def put_hdhr_queue(self, index, channel, status):
        if not self.config['hdhomerun']['disable_hdhr']:
            TunerHttpHandler.hdhr_queue.put(
                {'tuner': index, 'channel': channel, 'status': status})

    def read_buffer(self):
        video_data = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
        return video_data

    def write_buffer(self, msg):
        self.logger.debug('writing buffer-len={}'.format(len(msg)))
        self.wfile.write(msg)

    def do_tuning(self, sid):

        # sid is the id for the channel requested
        # with m3u8 redirect, there is no way to know when it is being used
        if self.config['player']['stream_type'] == 'm3u8redirect':
            channel_uri = self.locast.get_station_stream_uri(sid)
            if not channel_uri:
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))
            self.send_response(302)
            self.send_header('Location', channel_uri)
            self.end_headers()
            self.logger.info('Sending M3U8 file directly to client')
            return

        station_list = TunerHttpHandler.station_obj.get_dma_stations_and_channels()
        tuner_found = False
        self.bytes_per_read = int(int(self.config['main']['bytes_per_read']) / 1316) * 1316
        # keep track of how many tuners we can use at a time
        index = 0
        for index, scan_status in enumerate(TunerHttpHandler.rmg_station_scans):
            # the first idle tuner gets it
            if scan_status == 'Idle':
                try:
                    TunerHttpHandler.rmg_station_scans[index] = station_list[sid]['channel']
                    self.put_hdhr_queue(index, station_list[sid]['channel'], 'Stream')
                except KeyError:
                    self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))
                    self.logger.warning('KeyError on allocating idle tuner.  index={}, sid={}'
                        .format(index, sid))
                    return
                tuner_found = True
                break

        if tuner_found:
            if self.config['player']['stream_type'] == 'ffmpegproxy':
                self.send_response(200)
                self.send_header('Content-type', 'video/mp2t; Transfer-Encoding: chunked codecs="avc1.4D401E')
                self.end_headers()
                self.stream_video(sid, station_list)
                self.logger.info('Locast Connection Closed')
                TunerHttpHandler.rmg_station_scans[index] = 'Idle'
            elif self.config['player']['stream_type'] == 'internalproxy':
                self.send_response(200)
                self.send_header('Content-type', 'video/mp2t; Transfer-Encoding: chunked codecs="avc1.4D401E')
                self.end_headers()
                self.stream_direct(sid)
                self.logger.info('Locast Connection Closed')
                TunerHttpHandler.rmg_station_scans[index] = 'Idle'
            else:
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown streamtype'))
                self.logger.error('Unknown [player][stream_type] {}'
                    .format(self.config['player']['stream_type']))
        else:
            self.logger.warning('All tuners already in use')
            self.send_response(400, 'All tuners already in use.')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            reply_str = templates['htmlError'].format('All tuners already in use.')
            self.wfile.write(reply_str.encode('utf-8'))

    def stream_video(self, sid, station_list):
        if self.config['main']['quiet_print']:
            utils.block_print()
        channel_uri = self.locast.get_station_stream_uri(sid)
        if self.config['main']['quiet_print']:
            utils.enable_print()

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
                    if self.config['freeaccount']['is_free_account']:
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
        self.logger.debug('Terminating stream')
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
            ffprobe_command = [self.config['player']['ffprobe_path'],
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
            elif pkt_len < int(self.config['freeaccount']['min_pkt_rcvd']):
                # need to keep it from hitting bottom
                self.bytes_per_read = int(self.bytes_per_read * 1.5 / 1316) * 1316  # increase buffer size by 50%
                # self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                self.logger.debug('{} {}  {}{}'.format(
                    '### MIN pkts rcvd limit, adjusting READ BUFFER to =',
                    self.bytes_per_read,
                    'Pkts Rcvd=', pkt_len))
            elif pkt_len > int(self.config['freeaccount']['max_pkt_rcvd']):
                # adjust the byte read to keep the number of packets below 100
                # do not adjust up if packets are too low.
                self.bytes_per_read = int(self.bytes_per_read
                                          * int(self.config['freeaccount']['max_pkt_rcvd']) * 0.9
                                          / pkt_len / 1316) * 1316
                # self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                self.logger.debug('{} {}  {}{}'.format(
                    '### MAX pkts rcvd limit, adjusting READ BUFFER to =',
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
            pts_minimum = int(self.config['freeaccount']['pts_minimum'])
            if delta_pts > int(self.config['freeaccount']['pts_max_delta']) \
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
                self.logger.info('Stream reset')
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
                    > int(self.config['freeaccount']['pts_max_delta']):
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
        if self.config['freeaccount']['is_free_account']:
            delta_time = time.time() - self.last_refresh
            refresh_rate = int(self.config['freeaccount']['refresh_rate'])
            if refresh_rate > 0 and delta_time > int(self.config['freeaccount']['refresh_rate']):
                self.logger.info('Refresh time expired. Refresh rate is {} seconds'
                    .format(self.config['freeaccount']['refresh_rate']))
                return True
        return False

    #######
    # called when the refresh timeout occurs and the stream m3u8 file is updated
    def refresh_stream(self, sid, station_list):

        self.last_refresh = time.time()
        if self.config['main']['quiet_print']:
            utils.block_print()
        channel_uri = self.locast.get_station_stream_uri(sid)
        if self.config['main']['quiet_print']:
            utils.enable_print()
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
        service_name = self.config['epg']['epg_prefix'] + \
                       str(station_list[sid]['channel']) + \
                       self.config['epg']['epg_suffix'] + \
                       ' ' + station_list[sid]['friendlyName']
        return service_name

    def open_ffmpeg_proc(self, channel_uri, station_list, sid):
        ffmpeg_command = [self.config['main']['ffmpeg_path'],
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

    def stream_direct(self, sid):
        segments = OrderedDict()
        duration = 1
        file_filter = None
        self.last_refresh = time.time()
        stream_uri = self.locast.get_station_stream_uri(sid)
        if self.config['player']['stream_filter'] is not None:
            file_filter = re.compile(self.config['player']['stream_filter'])
        while True:
            try:
                added = 0
                removed = 0
                if self.is_time_to_refresh():
                    stream_uri = self.locast.get_station_stream_uri(sid)
                    self.last_refresh = time.time()
                playlist = m3u8.load(stream_uri)
                for segment_dict in list(segments.keys()):
                    is_found = False
                    for segment_m3u8 in playlist.segments:
                        uri = segment_m3u8.absolute_uri
                        if segment_dict == uri:
                            is_found = True
                            break
                    if not is_found:
                        del segments[segment_dict]
                        removed += 1
                        self.logger.debug(f"Removed {segment_dict} from play queue")
                        continue
                    else:
                        break

                for m3u8_segment in playlist.segments:
                    uri = m3u8_segment.absolute_uri
                    if uri not in segments:
                        played = False
                        if file_filter is not None:
                            m = file_filter.match(uri)
                            if m:
                                played = True
                        segments[uri] = {
                            'played': played,
                            'duration': m3u8_segment.duration
                        }
                        self.logger.debug(f"Added {uri} to play queue")
                        added += 1

                self.logger.debug(f"Added {added} new segments, removed {removed}")
                if added == 0 and duration > 0:
                    time.sleep(duration)

                for uri, data in segments.items():
                    if not data["played"]:
                        start_download = datetime.datetime.utcnow()
                        chunk = requests.get(uri).content
                        end_download = datetime.datetime.utcnow()
                        download_secs = (
                            end_download - start_download).total_seconds()
                        self.logger.debug(
                            f"Downloaded {uri}, time spent: {download_secs:.2f}")
                        data['played'] = True
                        if not chunk:
                            self.logger.warning(f"Segment {uri} not available. Skipping..")
                            continue
                        duration = data['duration']
                        runtime = (datetime.datetime.utcnow() - start_download).total_seconds()
                        target_diff = 0.5 * duration
                        wait = target_diff - runtime
                        self.logger.info(f"Serving {uri} ({duration}s) in, {wait:.2f}s")
                        self.write_buffer(chunk)
                        if wait > 0:
                            time.sleep(wait)
            except IOError as e:
                # Check we hit a broken pipe when trying to write back to the client
                if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                    # Normal process.  Client request end of stream
                    self.logger.info('2. Connection dropped by end device')
                    break
                else:
                    self.logger.error('{}{}'.format(
                        '3 UNEXPECTED EXCEPTION=', e))
                    raise
            except Exception as e:
                traceback.print_exc()
                break


class TunerHttpServer(Thread):

    def __init__(self, server_socket, config_obj, locast_service, location, _hdhr_queue):
        Thread.__init__(self)

        TunerHttpHandler.configObj = config_obj
        TunerHttpHandler.config = config_obj.data

        self.bind_ip = config_obj.data['main']['bind_ip']
        self.bind_port = config_obj.data['main']['plex_accessible_port']

        stations.Stations.config = config_obj.data
        stations.Stations.locast = locast_service
        stations.Stations.location = location
        TunerHttpHandler.station_obj = stations.Stations()
        TunerHttpHandler.locast = locast_service
        TunerHttpHandler.location = location
        TunerHttpHandler.hdhr_queue = _hdhr_queue

        # init station scans 
        tmp_rmg_scans = []
        for x in range(int(config_obj.data['main']['tuner_count'])):
            tmp_rmg_scans.append('Idle')
        TunerHttpHandler.rmg_station_scans = tmp_rmg_scans

        self.socket = server_socket
        self.start()

    def run(self):
        HttpHandlerClass = FactoryHttpHandler()
        httpd = HTTPServer((self.bind_ip, int(self.bind_port)), HttpHandlerClass, False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None
        httpd.serve_forever()


def FactoryHttpHandler():
    class CustomHttpHandler(TunerHttpHandler):
        def __init__(self, *args, **kwargs):
            super(CustomHttpHandler, self).__init__(*args, **kwargs)

    return CustomHttpHandler


def start(config, locast, location, hdhr_queue):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    config_copy = copy.deepcopy(config)
    config_obj = TVHUserConfig(config=config_copy)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config['main']['bind_ip'], int(config['main']['plex_accessible_port'])))
    server_socket.listen(int(config['main']['concurrent_listeners']))
    logger = logging.getLogger(__name__)
    logger.debug('Now listening for requests. Number of listeners={}'.format(config['main']['concurrent_listeners']))
    for i in range(int(config['main']['concurrent_listeners'])):
        TunerHttpServer(server_socket, config_obj, locast, location, hdhr_queue)
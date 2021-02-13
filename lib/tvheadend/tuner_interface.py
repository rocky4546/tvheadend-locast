import datetime, sys, json, os
import subprocess
import time
import errno
import socket
import urllib
import pathlib
import logging
import sched, time
from threading import Thread
import socket
import re
import mimetypes
import json
from io import StringIO
from http.server import HTTPServer
from urllib.parse import urlparse

import lib.stations as stations
import lib.tuner_interface
from lib.templates import templates
import lib.tvheadend.utils as utils
import lib.tvheadend.channels_m3u as channels_m3u
#from lib.tvheadend.stream_queue import StreamQueue

MIN_TIME_BETWEEN_LOCAST = 0.4

# with help from https://www.acmesystems.it/python_http
# and https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
class TVHeadendHttpHandler(lib.tuner_interface.PlexHttpHandler):

    # class variables
    # Either None or the UDP target
    # defines when the UDP stream is terminated for each instance of the http server
    udp_server_status = []
    udp_socket = None

    def __init__(self, *args):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
        self.ffmpeg_proc = None   # process for running ffmpeg
        self.block_moving_avg = 0
        self.bytes_per_read = 0
        self.last_refresh = None
        self.block_prev_pts = 0
        self.block_prev_time = None
        self.buffer_prev_time = None
        self.block_max_pts = 0
        self.small_pkt_streaming = False
        self.server_instance
        #self.stream_queue = None

        super().__init__(*args)
        logging.debug('Server Instance = {}'.format(self.server_instance))


    def read_buffer(self, sid, station_list):
        #videoData = self.stream_queue.read()
        videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
        return videoData

    def write_buffer(self, msg, protocol, addr):
        logging.debug('writing buffer-len={} protocol={} addr={}'.format(len(msg), protocol, addr))
        if protocol == 'TCP':
            self.wfile.write(msg)
        else:
            #break up the msg into 1316 byte packets?
            not_done = False
            offset = 0
            logging.debug('STARTING to transmit msg via UDP')
            while offset < len(msg):
                if len(msg) < offset + 1316:
                    TVHeadendHttpHandler.udp_socket.sendto(msg[offset:len(msg)], addr)
                    offset = len(msg)
                else:
                    TVHeadendHttpHandler.udp_socket.sendto(msg[offset:offset+1316], addr)
                    offset += 1316
                time.sleep(0.002)
            logging.debug('FINISHED sending msg via UDP')


    def do_GET(self):
        base_url = self.config['main']['plex_accessible_ip'] + ':' + self.config['main']['plex_accessible_port']
        contentPath = self.path

        # other urls:
        # discover.json (from HDHOMERUN DEVICE)
        #   {"FriendlyName":"HDHomeRun CONNECT QUATRO", 
        #   "ModelNumber":"HDHR5-4US", 
        #   "FirmwareName":"hdhomerun5_atsc", 
        #   "FirmwareVersion":"20200907", 
        #   "DeviceID":"xxxxxxxx", 
        #   "DeviceAuth":"xxxxxxxxxxxxxxxxxxxxxxxx", 
        #   "BaseURL":"http://xxx.xxx.x.xxx:80", 
        #   "LineupURL":"http://xxx.xxx.x.xxx:80/lineup.json", 
        #   "TunerCount":4}
        # what this program sends
        #   "{"FriendlyName": "{0}",
        #   "Manufacturer": "{0}",
        #   "ModelNumber": "{1}",
        #   "FirmwareName": "{2}",
        #   "TunerCount": {3},
        #   "FirmwareVersion": "{4}",
        #   "DeviceID": "{5}",
        #   "DeviceAuth": "locast2plex",
        #   "BaseURL": "http://{6}",
        #   "LineupURL": "http://{6}/lineup.json"}


        if contentPath == '/':
            self.send_response(302)
            self.send_header('Location', 'html/index.html')
            self.end_headers()

        elif contentPath == '/favicon.ico':
            self.send_response(302)
            self.send_header('Location', 'images/favicon.png')
            self.end_headers()

        elif contentPath == '/config.json':
            if self.config['main']['disable_web_config']:
                self.do_response(501, 'text/html', templates['htmlError'] \
                    .format('501 - Config pages disabled.  Set [main][disable_web_config] to False in the config file to enable'))
            else:
                self.do_response(200, 'application/json', json.dumps(self.configObj.filter_config_data()))

        elif contentPath == '/channels.m3u':
            self.do_response(200, 'audio/x-mpegurl', channels_m3u.get_channels_m3u(self.config, self.location, base_url))

        elif contentPath == '/playlist':
            self.send_response(302)
            self.send_header('Location', '/channels.m3u')
            self.end_headers()

        elif contentPath == '/lineup.json':  # TODO
            station_list = stations.get_dma_stations_and_channels(self.config, self.location)

            returnJSON = ''
            for index, list_key in enumerate(station_list):
                sid = str(list_key)
                returnJSON = returnJSON + templates['jsonLineupItem'].format(station_list[sid]['channel'], station_list[sid]['friendlyName'], base_url + '/watch/' + sid)
                if (index + 1) != len(station_list):
                    returnJSON = returnJSON + ','

            returnJSON = "[" + returnJSON + "]"
            self.do_response(200, 'application/json', returnJSON)
        elif contentPath.startswith('/images/'):
            if re.match(r'^[A-Za-z0-9\._\-/]+$', contentPath):
                htdocs_path = pathlib.Path(self.script_dir).joinpath('htdocs')
                file_path = pathlib.Path(htdocs_path).joinpath(*contentPath.split('/'))
                self.do_file_response(200, file_path)
            else:
                logging.warn('Invalid content. ignoring {}'.format(contentPath))
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Badly formed URL'))
        elif contentPath.startswith("/html/"):
            if re.match(r'^[A-Za-z0-9\._\-/]+$', contentPath):
                htdocs_path = pathlib.Path(self.script_dir).joinpath('htdocs')
                file_path = pathlib.Path(htdocs_path).joinpath(*contentPath.split('/'))
                self.do_file_response(200, file_path)
            else:
                logging.warn('Invalid content. ignoring {}'.format(contentPath))
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Badly formed URL'))
        elif contentPath.startswith('/auto/v'):
            channel = contentPath.replace('/auto/v', '')
            if '.' in channel:
                station_list = stations.get_dma_stations_and_channels(self.config, self.location)
                for station in station_list:
                    if station_list[station]['channel'] == channel:
                        self.do_tuning(station)
                        return
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))                
            else:
                self.do_tuning(channel)
        else:
            super().do_GET()
        return


    def do_POST(self):
        contentPath = self.path
        queryData = {}
        logging.debug('recieving a post form {}'.format(contentPath))
        if self.headers.get('Content-Length') != '0':
            postdata = self.rfile.read(int(self.headers.get('Content-Length'))).decode('utf-8')
            # if an input is empty, then it will remove it from the list when the dict is gen
            queryData = urllib.parse.parse_qs(postdata)
        if contentPath == '/html/configform.html':
            if self.config['main']['disable_web_config']:
                self.do_response(501, 'text/html', templates['htmlError'] \
                    .format('501 - Config pages disabled.  Set [main][disable_web_config] to False in the config file to enable'))
            else:
                #Take each key and make a [section][key] to store the value
                config_changes = {}
                for key in queryData:
                    key_pair = key.split('-')
                    if key_pair[0] not in config_changes:
                        config_changes[key_pair[0]] = {}
                    config_changes[key_pair[0]][key_pair[1]] = queryData[key]
                results = self.configObj.update_config(config_changes)
                self.do_response(200, 'text/html', results)
        elif contentPath == '/udp':
            (channel,) = queryData['channel']
            (target,) = queryData['target']
            (action,) = queryData['action']
            logging.debug('channel={} target={} action={}'.format(channel,target,action))
            if '.' in channel:
                station_list = stations.get_dma_stations_and_channels(self.config, self.location)
                try:
                    for station in station_list:
                        if station_list[station]['channel'] == channel:
                            logging.info('###### UDP player wanted, data is target={} channel={} action={} instance={}'.format(target,channel,action, self.server_instance))
                            self.process_udp_request(station, target, action)
                            return
                    self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))
                except KeyError:
                    self.do_response(501, 'text/html', templates['htmlError'].format('501 - Badly Formatted Message'))
            else:
                self.process_udp_request(channel, target, action)
                self.do_response(200, 'text/html', results)
        else:
            super().do_POST()
        return


    def process_udp_request(self, sid, target, action):
        if action == 'stream':
            # See if a stream is already running to the target
            if target in TVHeadendHttpHandler.udp_server_status:
                logging.debug('Server Instance = {}'.format(self.server_instance)) 
                # ignore request, instance is busy
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - UDP Target in use {}'))
            else:
                self.do_tuning(sid, protocol='UDP', target=target)
                #self.do_response(200, 'text/html', 'UDP stream started')
                #TVHeadendHttpHandler.udp_server_status[self.server_instance] = target
        else:
            # stop stream if running
            try:
                logging.debug('http server found, {} target removed'.format(self.server_instance))
                i = TVHeadendHttpHandler.udp_server_status.index(target)
                TVHeadendHttpHandler.udp_server_status[i] = None
                self.do_response(200, 'text/html', "UDP stream stopped")
            except ValueError:
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - UDP Stream not found {}'.format(self.server_instance)))


    def do_file_response(self, code, reply_file):
        if reply_file:
            try:
                f = open(reply_file, 'rb')
                mime_lookup = mimetypes.guess_type(str(reply_file))
                self.send_response(code)
                self.send_header('Content-type', mime_lookup)
                self.end_headers()
                self.wfile.write(f.read())
                f.close()
            except IsADirectoryError:
                self.do_response(401, 'text/html', templates['htmlError'].format('401 - Unauthorized'))
            except FileNotFoundError:
                self.do_response(404, 'text/html', templates['htmlError'].format('404 - Not Found'))
            


    def do_tuning(self, sid, protocol='TCP', target=None):
        #protocol = UDP, TCP
        #target = udp://host:port for UDP protocols only
        #sid is the id for the channel requested
        
        station_list = stations.get_dma_stations_and_channels(self.config, self.location)
        tuner_found = False
        self.bytes_per_read = int(int(self.config['main']['bytes_per_read']) / 1316) * 1316

        # keep track of how many tuners we can use at a time
        for index, scan_status in enumerate(self.rmg_station_scans):

            # the first idle tuner gets it
            if scan_status == 'Idle':
                try:
                    self.rmg_station_scans[index] = station_list[sid]['channel']
                except KeyError:
                    self.do_response(501, 'text/html', templates['htmlError'].format('501 - Unknown channel'))
                    logging.warning('KeyError on allocating idle tuner.  index={}, sid={}' \
                        .format(index, sid))
                    return
                
                tuner_found = True
                break

        if tuner_found:
            if protocol == 'TCP':
                self.send_response(200)
                self.send_header('Content-type', 'video/mp2t; Transfer-Encoding: chunked codecs="avc1.4D401E')
                self.end_headers()
                udp_address = None
                self.stream_video(sid, station_list, protocol, udp_address, index)
            else:
                logging.debug('Sending 200 response for UDP request')
                self.do_response(200, 'text/html', 'UDP stream started')
                logging.debug(target)
                TVHeadendHttpHandler.udp_server_status[self.server_instance] = target
                client = urlparse(target)
                udp_address = ( client.hostname, client.port )
                t = Thread(target=self.stream_video, args=(sid, station_list, protocol, udp_address, index))
                t.daemon = True
                t.start()
        else:
            logging.warn('All tuners already in use')
            self.send_response(400, 'All tuners already in use.')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            reply_str = templates['htmlError'].format('All tuners already in use.')
            self.wfile.write(reply_str.encode('utf-8'))


    def stream_video(self, sid, station_list, protocol, udp_address, tuner_id):
        if self.config['main']['quiet_print']:
            utils.block_print()
        channelUri = self.local_locast.get_station_stream_uri(sid)
        if self.config['main']['quiet_print']:
            utils.enable_print()


        self.ffmpeg_proc = self.open_ffmpeg_proc(channelUri, station_list, sid)
        
        # get initial videodata. if that works, then keep grabbing it
        videoData = self.read_buffer(sid, station_list)
        self.last_refresh = time.time()
        self.block_prev_time = time.time()
        self.buffer_prev_time = time.time()
        while True:
            if not videoData:
                logging.debug('No Video Data, refreshing stream')
                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                videoData = self.read_buffer(sid, station_list)
            else:
                # from https://stackoverflow.com/questions/9932332
                try:
                    if self.config['freeaccount']['is_free_account']:
                        videoData = self.check_pts(videoData, station_list, sid, protocol, udp_address)
                        
                    self.write_buffer(videoData, protocol, udp_address)
                    if protocol == 'UDP' and \
                            TVHeadendHttpHandler.udp_server_status[self.server_instance] is None:
                        logging.info('UDP Connection requested to be closed by client')
                        break
                        
                except IOError as e:
                    # Check we hit a broken pipe when trying to write back to the client
                    if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                        # Normal process.  Client request end of stream
                        logging.info('Connection dropped by end device')
                        break
                    else:
                        logging.error('{}{}'.format(
                            '1 UNEXPECTED EXCEPTION=', e))
                        raise

            try:
                videoData = self.read_buffer(sid, station_list)
            except Exception as e:
                logging.error('{}{}'.format(
                    '2 UNEXPECTED EXCEPTION=',e))
                
        # Send SIGTERM to shutdown ffmpeg
        logging.debug('Terminating stream')
        self.ffmpeg_proc.terminate()
        try:
            # ffmpeg writes a bit of data out to stderr after it terminates,
            # need to read any hanging data to prevent a zombie process.
            self.ffmpeg_proc.communicate()
        except ValueError:
            logging.info('Locast Connection Closed')

        self.rmg_station_scans[tuner_id] = 'Idle'

    
    #######
    # checks the PTS in the video stream.  If a bad PTS packet is found, 
    # it will update the video stream until the stream is valid.
    def check_pts(self, videoData, station_list, sid, protocol, udp_address):
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
            ptsout = cmdpts.communicate(videoData)[0]
            exit_code = cmdpts.wait()
            if exit_code != 0:
                logging.info('FFPROBE failed to execute with error code: {}' \
                    .format(exit_code))
            ptsjson = json.loads(ptsout)
            try:
                pkt_len = len(ptsjson['packets'])
            except KeyError:
                pkt_len = 0
            if pkt_len < 1:
                # This occurs when the buffer size is too small, so no video packets are sent
                logging.debug('Packet recieved with no video packet included')
                break
            elif pkt_len < int(self.config['freeaccount']['min_pkt_rcvd']):
                # need to keep it from hitting bottom
                self.bytes_per_read = int(self.bytes_per_read * 1.5 / 1316) * 1316 # increase buffer size by 50%
                #self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                logging.debug('{} {}  {}{}'.format(
                    '### MIN pkts rcvd limit, adjusting READ BUFFER to =', 
                    self.bytes_per_read, 
                    'Pkts Rcvd=', pkt_len))
            elif pkt_len > int(self.config['freeaccount']['max_pkt_rcvd']):
                # adjust the byte read to keep the number of packets below 100
                # do not adjust up if packets are too low.
                self.bytes_per_read = int(self.bytes_per_read 
                    * int(self.config['freeaccount']['max_pkt_rcvd']) * 0.9
                    / pkt_len / 1316) * 1316
                #self.stream_queue.set_bytes_per_read(self.bytes_per_read)
                logging.debug('{} {}  {}{}'.format(
                    '### MAX pkts rcvd limit, adjusting READ BUFFER to =', 
                    self.bytes_per_read, 
                    'Pkts Rcvd=', pkt_len))
                
            try:
                firstpts = ptsjson['packets'][0]['pts']
                endofjson = len(ptsjson['packets'])-1
                lastpts = ptsjson['packets'][endofjson]['pts']
            except KeyError:
                # Since we are requesting video only packets, this should not
                # happen, but it does, so do the same as if the pkt_len < 1
                logging.debug('KeyError exception: no pts in first packet, ignore')
                break
            
            deltapts = abs(lastpts-firstpts)
            logging.debug('{}{} {}{} {}{} {}{}'.format(
                    'First PTS=',ptsjson['packets'][0]['pts'],
                    'Last PTS=', lastpts,
                    'Delta=', deltapts,
                    'Pkts Rcvd=', pkt_len))
            pts_minimum = int(self.config['freeaccount']['pts_minimum'])
            if deltapts > int(self.config['freeaccount']['pts_max_delta']) \
                    or (lastpts < pts_minimum and not self.small_pkt_streaming):
                # PTS is 90,000 per second.
                # if delta is big, then this is bad PTS
                # PTS is setup to be current time on a 24 hour clock, so 
                # the bad packets that may be good are just after midnight; otherwise
                # it is a bad packet.
                # reset stream and try again.
                
                # need to determine if part of the stream obtained is good 
                # and should be sent
                if firstpts < pts_minimum:
                    if lastpts < pts_minimum:
                        # entire stream is bad and has small pts for entire stream
                        # happens mostly when the stream starts or restarts
                        self.small_pkt_streaming=True
                        logging.info('Small PTS for entire stream, drop and refresh buffer')
                        
                    else:
                        # RARE CASE
                        # first part of the stream is bad and
                        # end part of the stream is good
                        logging.info('Small PTS for with large PTS on end, drop and refresh buffer')
                elif lastpts < pts_minimum:
                    # RARE CASE
                    # first part of the stream is good
                    # but last part is a small pts
                    byte_offset = self.find_bad_pkt_offset(ptsjson)
                    if byte_offset > 0:
                        self.write_buffer(videoData[0:byte_offset], protocol, udp_address)
                        logging.info('{} {} {} {}'.format(
                            'Good PTS on front with small PTS on end.',
                            'Writing good bytes=', byte_offset, 
                            'out to client and refreshing buffer'))
                    else:
                        logging.info('Small PTS unknown case, drop and refreshing buffer')
                    
                else:
                    # MAIN CASE
                    # both pts are large, but delta is also too big
                    # Standard case which can occur every 15 minutes
                    byte_offset = self.find_bad_pkt_offset(ptsjson)
                    if byte_offset > 0:  # if -1, then offset was not found, drop everything
                        self.write_buffer(videoData[0:byte_offset], protocol, udp_address)
                        logging.info('{} {}{} {}'.format(
                            'Large delta PTS with good front.',
                            'Writing good bytes=', byte_offset, 
                            'out to client and double refreshing buffer'))
                    else:
                        logging.info('Large delta but no bad PTS ... unknown case, ignore')
                        break
                    
                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                self.block_prev_time = time.time()
                #videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                videoData = self.read_buffer(sid, station_list)
                logging.info('Stream reset')
            else:
                # valid video stream found
                if lastpts >= pts_minimum:
                    self.small_pkt_streaming=False
                
                # need to save time and determine if the delta from the last time was over x seconds
                # if it was, need to print out the PTS delta and reset the data.
                if self.block_prev_pts > 0 and time.time() - self.buffer_prev_time > MIN_TIME_BETWEEN_LOCAST:
                    if firstpts < self.block_max_pts - 20000:  # pkts are normally 3000-6000 pts apart for 720 broadcast and 9000-12000 for 480
                        # some packets are in the past
                        if lastpts < self.block_max_pts:
                            # all packets are in the past, drop and reload
                            logging.info('Entire PTS buffer in the past lastpts={} vs max={}'.format(lastpts, self.block_max_pts))
                            videoData = self.read_buffer(sid, station_list)
                        else:
                            # a potion of the packets are in the past.
                            # find the point and then write the end of the buffer to the stream
                            byte_offset = self.find_past_pkt_offset(ptsjson, self.block_max_pts)
                            logging.info('{} {}{} {}'.format(
                                'PTS buffer in the past.',
                                ' Writing end bytes from offset=', byte_offset, 
                                'out to client'))
                            if byte_offset < 0:
                                # means entire buffer is in the past. skip
                                pass
                            else:
                                # write end of buffer from byte_offset
                                self.write_buffer(videoData[byte_offset:len(videoData)-1], protocol, udp_address)
                            videoData = self.read_buffer(sid, station_list)
                    else:
                        
                        block_delta_time = time.time() - self.block_prev_time
                        self.buffer_prev_time = time.time()
                        block_pts_delta = firstpts - self.block_prev_pts
                        self.block_prev_time = time.time()
                        self.block_prev_pts = firstpts
                        # calculate a running average
                        if self.block_moving_avg == 0:
                            self.block_prev_pts = firstpts
                            self.block_moving_avg = 10 * block_pts_delta # 10 point moving average
                        self.block_moving_avg = self.block_moving_avg / 10*9 + block_pts_delta
                        logging.debug('BLOCK PTS moving average = {}   BLOCK DELTA time = {}'.format(
                                int(self.block_moving_avg/10), block_delta_time)
                                
                            )
                        if lastpts > self.block_max_pts:
                            self.block_max_pts = lastpts
                        break
                else:
                    if self.block_prev_pts == 0:
                        self.block_prev_pts = firstpts
                        self.block_max_pts = lastpts
                    # determine how much pts has occurred since the last reset
                    block_pts_delta = lastpts - self.block_prev_pts
                    self.buffer_prev_time = time.time()

                    # TBD TBD TBD TBD TBD
                    # determine if the pts is in the past
                    if lastpts < self.block_max_pts - 50000:
                        logging.info('PTS in the past {} vs max={}'.format(lastpts, self.block_max_pts))
                        # need to read the next buffer and loop around
                        videoData = self.read_buffer(sid, station_list)
                    
                    # determine if we are at the end of a block AND the refresh timeout has occurred.
                    elif block_pts_delta > self.block_moving_avg/10:
                        if self.is_time_to_refresh():
                            # write out whatever we have a refresh the stream
                            if lastpts > self.block_max_pts:
                                self.block_max_pts = lastpts
                            self.write_buffer(videoData, protocol, udp_address)
                            self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                            videoData = self.read_buffer(sid, station_list)
                            # loop back around and verify the videoData is good
                        else:
                            if lastpts > self.block_max_pts:
                                self.block_max_pts = lastpts
                            break
                    else:
                        if lastpts > self.block_max_pts:
                            self.block_max_pts = lastpts
                        break
        return videoData


    def find_bad_pkt_offset(self, ptsjson):
        num_of_pkts = len(ptsjson['packets']) - 1    # index from 0 to len - 1
        i=1
        prev_pkt_dts = ptsjson['packets'][0]['pts']
        byte_offset = -1
        while i < num_of_pkts:
            next_pkt_pts = ptsjson['packets'][i]['pts']
            if abs(next_pkt_pts - prev_pkt_dts) \
                    > int(self.config['freeaccount']['pts_max_delta']):
                # found place where bad packets start
                # only video codecs have byte position info
                byte_offset = int(int(ptsjson['packets'][i]['pos']) / 1316 ) * 1316
                logging.debug('{}{}'.info('Bad PTS at byte_offset=', prev_pkt_dts))
                break
                    
            i += 1
            prev_pkt_dts = next_pkt_pts
        return byte_offset

        
    def find_past_pkt_offset(self, ptsjson, block_max_pts):
        num_of_pkts = len(ptsjson['packets']) - 1    # index from 0 to len - 1
        next_pkt_pts = 0
        i=0
        byte_offset = -1
        while i < num_of_pkts:
            prev_pkt_dts = next_pkt_pts
            next_pkt_pts = ptsjson['packets'][i]['pts']
            if next_pkt_pts >= block_max_pts-6000:  # at 720, a pkt is 3000-6000 in size.  Need to back up one pkt.
                # found place where future packets start
                # only video codecs have byte position info
                byte_offset = int(int(ptsjson['packets'][i]['pos']) / 1316) * 1316
                logging.debug('{}{} {}{} {}{}'.format('Future PTS at byte_offset=', byte_offset, 'pkt_pts=', next_pkt_pts, 'prev_pkt=', prev_pkt_dts))
                break
                    
            i += 1
        return byte_offset

        
    def is_time_to_refresh(self):
        if self.config['freeaccount']['is_free_account']:
            delta_time = time.time() - self.last_refresh
            refresh_rate = int(self.config['freeaccount']['refresh_rate'])
            if refresh_rate > 0 and delta_time > int(self.config['freeaccount']['refresh_rate']):
                logging.info('Refresh time expired. Refresh rate is {} seconds'
                    .format(self.config['freeaccount']['refresh_rate']))
                return True
        return False


    #######
    # called when the refresh timeout occurs and the stream m3u8 file is updated
    def refresh_stream(self, sid, station_list):

        self.last_refresh = time.time()
        if self.config['main']['quiet_print']:
            utils.block_print()
        channelUri = self.local_locast.get_station_stream_uri(sid)
        if self.config['main']['quiet_print']:
            utils.enable_print()
        try:
            self.ffmpeg_proc.terminate()
            self.ffmpeg_proc.wait(timeout=0.1)
            logging.debug('Previous ffmpeg terminated')
        except ValueError:
            pass
        except subprocess.TimeoutExpired:
            # try one more time.  If the process does not terminate
            # a socket error will occur with locast having 2 connections.
            self.ffmpeg_proc.terminate()
            time.sleep(0.1)
        
        logging.debug('{}{}'.format(
            'Refresh Stream channelUri=',channelUri))
        ffmpeg_process = self.open_ffmpeg_proc(channelUri, station_list, sid)
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
  
  
    def open_ffmpeg_proc(self, channelUri, station_list, sid):
        ffmpeg_command = [self.config['main']['ffmpeg_path'],
                            '-i', str(channelUri),
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
        #self.stream_queue = StreamQueue(ffmpeg_process.stdout, self.bytes_per_read, ffmpeg_process)
        return ffmpeg_process
    
    def set_server_index(self, index):
        logging.debug('Setting server instance to {}'.format(index))
        self.server_instance = index

# mostly from https://github.com/ZeWaren/python-upnp-ssdp-example
# and https://stackoverflow.com/questions/46210672/python-2-7-streaming-http-server-supporting-multiple-connections-on-one-port
class TVHeadendHttpServer(Thread):

    def __init__(self, serverSocket, configObj, locast_service, location, _index):
        Thread.__init__(self)

        TVHeadendHttpHandler.configObj = configObj
        TVHeadendHttpHandler.config = configObj.data

        self.bind_ip = configObj.data['main']['bind_ip']
        self.bind_port = configObj.data['main']['bind_port']

        TVHeadendHttpHandler.stations = stations
        TVHeadendHttpHandler.local_locast = locast_service
        TVHeadendHttpHandler.location = location

        # init station scans 
        tmp_rmg_scans = []
        for x in range(int(configObj.data['main']['tuner_count'])):
            tmp_rmg_scans.append('Idle')

        tmp_udp_status = []
        for x in range(int(configObj.data['main']['concurrent_listeners'])):
            tmp_udp_status.append(None)

        tmp_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        tmp_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                tmp_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except socket.error as le:
                # RHEL6 defines SO_REUSEPORT but it doesn't work
                if le.errno == ENOPROTOOPT:
                    pass
                else:
                    raise
        
        TVHeadendHttpHandler.rmg_station_scans = tmp_rmg_scans
        TVHeadendHttpHandler.udp_server_status = tmp_udp_status
        TVHeadendHttpHandler.udp_socket = tmp_udp_socket
        
        self.index = _index
        self.socket = serverSocket

        self.daemon = True
        self.start()

    def run(self):
        HttpHandlerClass = FactoryHttpHandler(self.index)
        httpd = HTTPServer((self.bind_ip, int(self.bind_port)), HttpHandlerClass, False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None

        httpd.serve_forever()

def FactoryHttpHandler(index):
    class CustomHttpHandler(TVHeadendHttpHandler):
        def __init__(self, *args, **kwargs):
            self.set_server_index(index)
            super(CustomHttpHandler, self).__init__(*args, **kwargs)
    return CustomHttpHandler


def start(configObj, locast, location):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    config = configObj.data
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSocket.bind((config['main']['bind_ip'], int(config['main']['bind_port'])))
    serverSocket.listen(int(config['main']['concurrent_listeners']))

    logging.debug('Now listening for requests. Number of listeners={}'.format(config['main']['concurrent_listeners']))
    for i in range(int(config['main']['concurrent_listeners'])):
        TVHeadendHttpServer(serverSocket, configObj, locast, location, i)

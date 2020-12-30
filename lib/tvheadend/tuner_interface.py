import datetime, sys, json
import subprocess
import threading
import time
import errno
import socket
import urllib
import pathlib
import logging
import sched, time, threading
import socket
from io import StringIO
from http.server import HTTPServer

import lib.stations as stations
import lib.tuner_interface
from lib.templates import templates
import lib.tvheadend.utils as utils
import lib.tvheadend.channels_m3u as channels_m3u

# with help from https://www.acmesystems.it/python_http
# and https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
class TVHeadendHttpHandler(lib.tuner_interface.PlexHttpHandler):

    # using class variables since this should only be set once
    ffmpeg_proc = None   # process for running ffmpeg
    bytes_per_read = 0
    last_refresh = None
    block_prev_pts = 0
    block_prev_time = None
    buffer_prev_time = None
    block_moving_avg = 0
    block_max_pts = 0
    small_pkt_streaming=False


    def do_GET(self):
        if self.config['main']['plex_accessible_ip'] == "0.0.0.0":
            print(self.client_address[0], self.get_ip(self.client_address[0]))
            base_url = self.get_ip(self.client_address[0]) + ':' + self.config['main']['plex_accessible_port']
        else:
            base_url = self.config['main']['plex_accessible_ip'] + ':' + self.config['main']['plex_accessible_port']
        contentPath = self.path

        if contentPath == '/channels.m3u':
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


        else:
            super().do_GET()
        return


    def do_tuning(self, sid):
        if self.config['main']['quiet_print']:
            utils.block_print()
        channelUri = self.local_locast.get_station_stream_uri(sid)
        if self.config['main']['quiet_print']:
            utils.enable_print()
        
        station_list = stations.get_dma_stations_and_channels(self.config, self.location)
        tuner_found = False
        self.bytes_per_read = int(self.config['main']['bytes_per_read'])

        # keep track of how many tuners we can use at a time
        for index, scan_status in enumerate(self.rmg_station_scans):

            # the first idle tuner gets it
            if scan_status == 'Idle':
                self.rmg_station_scans[index] = station_list[sid]['channel']
                tuner_found = True
                break

        if tuner_found:
            self.send_response(200)
            self.send_header('Content-type', 'video/mpeg; codecs="avc1.4D401E')
            self.end_headers()
            self.ffmpeg_proc = self.open_ffmpeg_proc(channelUri, station_list, sid)
            
            # get initial videodata. if that works, then keep grabbing it
            videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
            self.last_refresh = time.time()
            self.block_prev_time = time.time()
            self.buffer_prev_time = time.time()
            while True:
                if not videoData:
                    logging.debug('No Video Data, refreshing stream')
                    self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                    videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                else:
                    # from https://stackoverflow.com/questions/9932332
                    try:
                        if self.config['main']['is_free_account']:
                            videoData = self.check_pts(videoData, station_list, sid)
                            
                        self.wfile.write(videoData)
                    except IOError as e:
                        # Check we hit a broken pipe when trying to write back to the client
                        if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                            # Normal process.  Client request end of stream
                            logging.info('Connection dropped by end device')
                            break
                        else:
                            logging.error('{}{}'.format(
                                'UNEXPECTED EXCEPTION=',sys.exc_info()[0]))
                            raise

                try:
                    videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                except:
                    logging.error('{}{}'.format(
                        'UNEXPECTED EXCEPTION=',sys.exc_info()[0]))
                    
            # Send SIGTERM to shutdown ffmpeg
            logging.info('Terminating stream')
            self.ffmpeg_proc.terminate()
            try:
                # ffmpeg writes a bit of data out to stderr after it terminates,
                # need to read any hanging data to prevent a zombie process.
                self.ffmpeg_proc.communicate()
            except ValueError:
                logging.info('Locast Connection Closed')

            self.rmg_station_scans[index] = 'Idle'

        else:
            logging.warn('All tuners already in use')
            self.send_response(400, 'All tuners already in use.')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            reply_str = templates['htmlError'].format('All tuners already in use.')
            self.wfile.write(reply_str.encode('utf-8'))

    
    #######
    # checks the PTS in the video stream.  If a bad PTS packet is found, 
    # it will update the video stream until the stream is valid.
    def check_pts(self, videoData, station_list, sid):
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
            cmdpts.stdin.write(videoData)
            ptsout = cmdpts.communicate()[0]
            ptsjson = json.loads(ptsout)
            pkt_len = len(ptsjson['packets'])
            if pkt_len < 1:
                # This occurs when the buffer size is too small, so no video packets are sent
                logging.debug('Packet recieved with no video packet included')
                break
            elif pkt_len < int(self.config['freeaccount']['min_pkt_rcvd']):
                # need to keep it from hitting bottom
                self.bytes_per_read = int(self.bytes_per_read * 1.5) # increase buffer size by 50%
                logging.debug('{} {}  {}{}'.format(
                    '### MIN pkts rcvd limit, adjusting READ BUFFER to =', 
                    self.bytes_per_read, 
                    'Pkts Rcvd=', pkt_len))
            elif pkt_len > int(self.config['freeaccount']['max_pkt_rcvd']):
                # adjust the byte read to keep the number of packets below 100
                # do not adjust up if packets are too low.
                self.bytes_per_read = int(self.bytes_per_read 
                    * int(self.config['freeaccount']['max_pkt_rcvd']) * 0.9
                    / pkt_len)
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
                        logging.debug('Small PTS for entire stream, drop and refresh buffer')
                        
                    else:
                        # RARE CASE
                        # first part of the stream is bad and
                        # end part of the stream is good
                        logging.debug('Small PTS for with large PTS on end, drop and refresh buffer')
                elif lastpts < pts_minimum:
                    # RARE CASE
                    # first part of the stream is good
                    # but last part is a small pts
                    byte_offset = self.find_bad_pkt_offset(ptsjson)
                    if byte_offset > 0:
                        self.wfile.write(videoData[0:byte_offset])
                        logging.debug('{} {} {} {}'.format(
                            'Good PTS on front with small PTS on end.',
                            'Writing good bytes=', byte_offset, 
                            'out to client and refreshing buffer'))
                    else:
                        logging.debug('Small PTS unknown case, drop and refreshing buffer')
                    
                else:
                    # MAIN CASE
                    # both pts are large, but delta is also too big
                    # Standard case which can occur every 15 minutes
                    byte_offset = self.find_bad_pkt_offset(ptsjson)
                    if byte_offset > 0:  # if -1, then offset was not found, drop everything
                        self.wfile.write(videoData[0:byte_offset])
                        logging.debug('{} {}{} {}'.format(
                            'Large delta PTS with good front.',
                            'Writing good bytes=', byte_offset, 
                            'out to client and double refreshing buffer'))
                    else:
                        logging.debug('Large delta but no bad PTS ... unknown case, ignore')
                        break
                    
                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                self.block_prev_time = time.time()
                videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                logging.info('Stream reset')
            else:
                # valid video stream found
                if lastpts >= pts_minimum:
                    self.small_pkt_streaming=False
                
                # need to save time and determine if the delta from the last time was over x seconds
                # if it was, need to print out the PTS delta and reset the data.
                if self.block_prev_pts > 0 and time.time() - self.buffer_prev_time > 0.25:
                    if firstpts < self.block_max_pts - 20000:  # pkts are normally 3000-6000 pts apart for 720 broadcast and 9000-12000 for 480
                        # some packets are in the past
                        if lastpts < self.block_max_pts:
                            # all packets are in the past, drop and reload
                            logging.debug('Entire PTS buffer in the past lastpts={} vs max={}'.format(lastpts, self.block_max_pts))
                            videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                        else:
                            # a potion of the packets are in the past.
                            # find the point and then write the end of the buffer to the stream
                            byte_offset = self.find_past_pkt_offset(ptsjson, self.block_max_pts)
                            logging.debug('{} {}{} {}'.format(
                                'PTS buffer in the past.',
                                ' Writing end bytes from offset=', byte_offset, 
                                'out to client'))
                            if byte_offset < 0:
                                # means entire buffer is in the past. skip
                                pass
                            else:
                                # write end of buffer from byte_offset
                                self.wfile.write(videoData[byte_offset:len(videoData)-1])
                            videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
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
                        logging.debug('PTS in the past {} vs max={}'.format(lastpts, self.block_max_pts))
                        # need to read the next buffer and loop around
                        videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                    
                    # determine if we are at the end of a block AND the refresh timeout has occurred.
                    elif block_pts_delta > self.block_moving_avg/10:
                        if self.is_time_to_refresh():
                            # write out whatever we have a refresh the stream
                            if lastpts > self.block_max_pts:
                                self.block_max_pts = lastpts
                            self.wfile.write(videoData)
                            self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                            videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
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
                byte_offset = int(ptsjson['packets'][i]['pos']) - 1
                logging.debug('{}{}'.format('Bad PTS at byte_offset=', prev_pkt_dts))
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
                byte_offset = int(ptsjson['packets'][i]['pos'])
                logging.debug('{}{} {}{} {}{}'.format('Future PTS at byte_offset=', byte_offset, 'pkt_pts=', next_pkt_pts, 'prev_pkt=', prev_pkt_dts))
                break
                    
            i += 1
        return byte_offset

        
    def is_time_to_refresh(self):
        if self.config['main']['is_free_account']:
            delta_time = time.time() - self.last_refresh
            refresh_rate = int(self.config['freeaccount']['refresh_rate'])
            if refresh_rate > 0 and delta_time > int(self.config['freeaccount']['refresh_rate']):
                logging.debug('Refresh time expired. Refresh rate is {} seconds'
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
        return ffmpeg_process
    
    def get_ip(self, client_ip):
        hostname = socket.gethostname()
        IP = socket.gethostbyname(hostname)
        return IP



# mostly from https://github.com/ZeWaren/python-upnp-ssdp-example
# and https://stackoverflow.com/questions/46210672/python-2-7-streaming-http-server-supporting-multiple-connections-on-one-port
class TVHeadendHttpServer(threading.Thread):

    def __init__(self, serverSocket, config, locast_service, location):
        threading.Thread.__init__(self)

        TVHeadendHttpHandler.config = config

        self.bind_ip = config['main']['bind_ip']
        self.bind_port = config['main']['bind_port']

        TVHeadendHttpHandler.stations = stations
        TVHeadendHttpHandler.local_locast = locast_service
        TVHeadendHttpHandler.location = location

        # init station scans 
        tmp_rmg_scans = []

        for x in range(int(config['main']['tuner_count'])):
            tmp_rmg_scans.append('Idle')
        
        TVHeadendHttpHandler.rmg_station_scans = tmp_rmg_scans

        self.socket = serverSocket

        self.daemon = True
        self.start()

    def run(self):
        httpd = HTTPServer((self.bind_ip, int(self.bind_port)), TVHeadendHttpHandler, False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None

        httpd.serve_forever()


def start(config, locast, location):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serverSocket.bind((config['main']['bind_ip'], int(config['main']['bind_port'])))
    serverSocket.listen(int(config['main']['concurrent_listeners']))

    logging.debug('Now listening for requests. Number of listeners={}'.format(config['main']['concurrent_listeners']))
    for i in range(int(config['main']['concurrent_listeners'])):
        TVHeadendHttpServer(serverSocket, config, locast, location)

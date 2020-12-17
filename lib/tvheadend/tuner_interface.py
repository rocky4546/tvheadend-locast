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
from io import StringIO
from http.server import HTTPServer

import lib.stations as stations
import lib.tuner_interface
import lib.tvheadend.utils as utils

# with help from https://www.acmesystems.it/python_http
# and https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
class TVHeadendHttpHandler(lib.tuner_interface.PlexHttpHandler):

    # using class variables since this should only be set once
    ffmpeg_proc = None   # process for running ffmpeg
    bytes_per_read = 0


    def do_tuning(self, sid):
        if self.config["main"]["quiet_print"]:
            utils.block_print()
        channelUri = self.local_locast.get_station_stream_uri(sid)
        if self.config["main"]["quiet_print"]:
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
            ffmpeg_command = [self.config['main']['ffmpeg_path'],
                                "-i", channelUri,
                                "-c:v", "copy",
                                "-c:a", "copy",
                                "-f", "mpegts",
                                "-nostats", 
                                "-hide_banner",
                                "-loglevel", "warning",
                                "-metadata", "service_provider=Locast",
                                "-metadata", "service_name="+self.set_service_name(station_list, sid),
                                "-copyts", # added for free account pts processing
                                "pipe:1"]
            self.ffmpeg_proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
            
            # get initial videodata. if that works, then keep grabbing it
            videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
            while True:
                if not videoData:
                    logging.debug("No Video Data, refreshing stream")
                    # this happens when locast stops, so need to refresh m3u
                    self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                    videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                else:
                    # from https://stackoverflow.com/questions/9932332
                    try:
                        if not self.config['main']['is_free_account']:
                            videoData = self.check_pts(videoData, station_list, sid)
                        self.wfile.write(videoData)
                        time.sleep(0.1) # delay per stream grab. Should be a number from 0.1 to 0.5
                    except IOError as e:
                        # Check we hit a broken pipe when trying to write back to the client
                        if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                            # Normal process.  Client request end of stream
                            logging.info("Connection dropped by end device")
                            break
                        else:
                            logging.error('{}{}'.format(
                                'UNEXPECTED EXCEPTION=',sys.exc_info()[0]))
                            raise

                try:
                    videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                except:
                    logging.error('{}{}'.format(
                        "UNEXPECTED EXCEPTION=",sys.exc_info()[0]))
                    
            # Send SIGTERM to shutdown ffmpeg
            logging.info("Terminating stream")
            self.ffmpeg_proc.terminate()
            try:
                # ffmpeg writes a bit of data out to stderr after it terminates,
                # need to read any hanging data to prevent a zombie process.
                self.ffmpeg_proc.communicate()
            except ValueError:
                logging.info("Locast Connection Closed")

            self.rmg_station_scans[index] = 'Idle'

        else:
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
            cmdpts = subprocess.Popen(['ffprobe', 
                    '-print_format', 'json', 
                    '-v', 'quiet', '-show_packets',
                    '-select_streams', 'v:0',
                    '-show_entries', 'side_data=:packet=pts,pos',
                    '-'],
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
                logging.debug('{} {} {}{}'.format(
                    'Min pkts rcvd limit, adjusting read buffer to', 
                    self.bytes_per_read, 
                    'pkts rcvd=', pkt_len))
            elif pkt_len > int(self.config['freeaccount']['max_pkt_rcvd']):
                # adjust the byte read to keep the number of packets below 100
                # do not adjust up if packets are too low.
                self.bytes_per_read = int(self.bytes_per_read 
                    * int(self.config['freeaccount']['max_pkt_rcvd']) * 0.9
                    / pkt_len)
                logging.debug('{} {} {}{}'.format(
                    'Max pkts rcvd limit, adjusting read buffer to', 
                    self.bytes_per_read, 
                    'pkts rcvd=', pkt_len))
                
            firstpts = ptsjson['packets'][0]['pts']
            endofjson = len(ptsjson['packets'])-1
            lastpts = ptsjson['packets'][endofjson]['pts']
            deltapts = abs(lastpts-firstpts)
            logging.debug('{}{} {}{} {}{} {}{}'.format(
                    'First PTS=',ptsjson['packets'][0]['pts'],
                    'Last PTS=', lastpts,
                    'Delta=', deltapts,
                    'Pkts Rcvd=', pkt_len))
            pts_minimum = int(self.config['freeaccount']['pts_minimum'])
            if deltapts > int(self.config['freeaccount']['pts_max_delta']) \
                    or lastpts < pts_minimum:
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
                            'out to client and refreshing buffer'))
                    else:
                        logging.debug('Large delta PTS unknown case, drop and refreshing buffer')
                        
                    
                self.ffmpeg_proc = self.refresh_stream(sid, station_list)
                videoData = self.ffmpeg_proc.stdout.read(self.bytes_per_read)
                logging.info("Stream reset")
            else:
                # valid video stream found
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
                break
                    
            i += 1
            prev_pkt_dts = next_pkt_pts
        return byte_offset

    #######
    # called when the refresh timeout occurs and the stream m3u8 file is updated
    def refresh_stream(self, sid, station_list):

        if self.config["main"]["quiet_print"]:
            utils.block_print()
        channelUri = self.local_locast.get_station_stream_uri(sid)
        if self.config["main"]["quiet_print"]:
            utils.enable_print()
        logging.debug("Restarting ffmpeg")
        try:
            self.ffmpeg_proc.terminate()
            while True:
                if self.ffmpeg_proc.poll() == None:
                    time.sleep(0.01) # allow for other processes to run
                    self.ffmpeg_proc.terminate()
                else:
                    logging.debug("ffmpeg terminated")
                    break
        except ValueError:
            pass

        logging.debug('{}{}'.format(
            "Refresh Stream channelUri=",channelUri))
        ffmpeg_command = [self.config['main']['ffmpeg_path'],
                            "-i", channelUri,
                            "-c:v", "copy",
                            "-c:a", "copy",
                            "-f", "mpegts",
                            "-nostats", 
                            "-hide_banner",
                            "-loglevel", "warning",
                            "-metadata", "service_provider=Locast",
                            "-metadata", "service_name="+self.set_service_name(station_list, sid),
                            "-copyts",
                            "pipe:1"]
        return subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)

    #######
    # returns the service name used to sync with the EPG channel name
    def set_service_name(self, station_list, sid):
        service_name = self.config['epg']['epg_prefix'] + \
            str(station_list[sid]['channel']) + \
            self.config['epg']['epg_suffix'] + \
            " " + station_list[sid]['friendlyName']
        return service_name
  
    
    

# mostly from https://github.com/ZeWaren/python-upnp-ssdp-example
# and https://stackoverflow.com/questions/46210672/python-2-7-streaming-http-server-supporting-multiple-connections-on-one-port
class TVHeadendHttpServer(threading.Thread):

    def __init__(self, serverSocket, config, locast_service, location):
        threading.Thread.__init__(self)

        TVHeadendHttpHandler.config = config

        self.bind_ip = config["main"]["bind_ip"]
        self.bind_port = config["main"]["bind_port"]

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
    serverSocket.bind((config["main"]['bind_ip'], int(config["main"]['bind_port'])))
    serverSocket.listen(int(config["main"]["concurrent_listeners"]))

    logging.debug("Now listening for requests.")
    for i in range(int(config["main"]["concurrent_listeners"])):
        TVHeadendHttpServer(serverSocket, config, locast, location)

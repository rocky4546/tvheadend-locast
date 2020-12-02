import datetime, sys, json
import subprocess
import threading
import time
import errno
import socket
import urllib
import pathlib
import sched, time, threading
from io import StringIO
from http.server import HTTPServer

import lib.stations as stations
import lib.tuner_interface


# with help from https://www.acmesystems.it/python_http
# and https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
class TVHeadendHttpHandler(lib.tuner_interface.PlexHttpHandler):

    # using class variables since this should only be set once
    ffmpeg_proc = None   # process for running ffmpeg
    start_time = None    # last time the stream was refreshed for free accounts




    def do_tuning(self, sid):
        channelUri = self.local_locast.get_station_stream_uri(sid)
        station_list = stations.get_dma_stations_and_channels(self.config, self.location)
        tuner_found = False

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
                                "-metadata", "service_provider=Locast",  #CAM
                                "-metadata", "service_name="+self.setServiceName(station_list, sid),    #CAM
                                "-copyts",
                                "pipe:1"]
            self.ffmpeg_proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
            testtime=str(int(time.time()))
            testfilename = 'locaststream'+testtime+'.ts'
            print(datetime.datetime.now(),"##### CAM5 opening new file", testfilename)
            testfile = open(testfilename, 'w+b')

            # get initial videodata. if that works, then keep grabbing it
            videoData = self.ffmpeg_proc.stdout.read(int(self.config['main']['bytes_per_read']))
            self.start_time = time.time()  #CAM
            time.sleep(3.0) #CAM wait to allow a buffer to accumulate            
            while True:
                if not videoData:
                    print(datetime.datetime.now(),"No Video Data, refreshing stream")
                    # this happens when locast stops, so need to refresh m3u
                    self.ffmpeg_proc = self.refreshStream(sid, station_list, -1)  #CAM
                    self.start_time = time.time()  #CAM
                    videoData = self.ffmpeg_proc.stdout.read(int(self.config['main']['bytes_per_read']))
                else:
                    # from https://stackoverflow.com/questions/9932332
                    try:
#                        print(datetime.datetime.now(),"##### CAM2 stream=",len(videoData))
                        videoData = self.checkPTS(videoData, station_list, sid)
                        
                        self.wfile.write(videoData)
                        testfile.write(videoData)
                        time.sleep(0.3) # delay per stream grab
#                        print(datetime.datetime.now(),"##### CAM3")
                    except IOError as e:
                        # Check we hit a broken pipe when trying to write back to the client
                        if e.errno in [errno.EPIPE, errno.ECONNABORTED, errno.ECONNRESET, errno.ECONNREFUSED]:
                            # Normal process.  Client request end of stream
                            print(datetime.datetime.now(),"Connection dropped by end device")
                            break
                        else:
                            print(datetime.datetime.now(),"unknown error")
                            raise

                ####### CAM CAM CAM CAM new refresh code
                # this is where we need to put something to refresh the ffmpeg command
                if self.config['main']['is_free_account']:  #CAM
#                    print(datetime.datetime.now(),"##### CAM4 checking refresh time")
                    delta_time = time.time() - self.start_time  #CAM
                    if delta_time > int(self.config['main']['free_refresh_rate']):  #CAM
                        self.ffmpeg_proc = self.refreshStream(sid, station_list, -1)  #CAM
                        self.start_time = time.time()  #CAM

#                print(datetime.datetime.now(),"##### CAM1")
                try:
                    videoData = self.ffmpeg_proc.stdout.read(int(self.config['main']['bytes_per_read']))
                except:
                    print("##### CAM6 UNEXPECTED EXCEPTION=",sys.exc_info()[0])
                    
#                print(datetime.datetime.now(),"##### CAM grab next stream=",len(videoData))


            # Send SIGTERM to shutdown ffmpeg
            print(datetime.datetime.now(),"terminating stream")
            self.ffmpeg_proc.terminate()
            try:
                # ffmpeg writes a bit of data out to stderr after it terminates,
                # need to read any hanging data to prevent a zombie process.
                self.ffmpeg_proc.communicate()
            except ValueError:
                print(datetime.datetime.now(),"Connection Closed")

            self.rmg_station_scans[index] = 'Idle'

        else:
            self.send_response(400, 'All tuners already in use.')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            reply_str = templates['htmlError'].format('All tuners already in use.')
            self.wfile.write(reply_str.encode('utf-8'))

 
    
    ####### CAM CAM CAM CAM new procedure
    # checks the PTS in the video stream.  If a bad PTS packet is found, 
    # it will update the video stream until the stream is valid.
    def checkPTS(self, videoData, station_list, sid):
        while True:
            # check the dts in videoData to see if we should throw it away
            cmdpts = subprocess.Popen(['ffprobe', 
                    '-print_format', 'json', 
                    '-v', 'quiet', '-show_packets',
                    '-show_entries', 'side_data=:packet=pts',
                    '-'], 
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            cmdpts.stdin.write(videoData)
            ptsout = cmdpts.communicate()[0]
            ptsjson = json.loads(ptsout)
            firstpts = ptsjson['packets'][0]['pts']
            endofjson = len(ptsjson['packets'])-1
            lastpts = ptsjson['packets'][endofjson]['pts']
            deltapts = abs(lastpts-firstpts)
            print('############################### CAM FIRST_JSON= ',ptsjson['packets'][0]['pts'],
                    "   LAST_JSON=", lastpts,
                    "   DELTA=", deltapts)
            if (deltapts > 5000000 or lastpts < 10000000):             
                # PTS is 90,000 per second.
                # if delta is big, then this is bad PTS
                # PTS is setup to be current time on a 24 hour clock, so 
                # the bad packets that may be good are just after midnight; otherwise
                # it is a bad packet.
                # reset stream and try again.
                self.ffmpeg_proc = self.refreshStream(sid, station_list, -1)  #CAM
                self.start_time = time.time()  #CAM
                videoData = self.ffmpeg_proc.stdout.read(int(self.config['main']['bytes_per_read']))
                print(datetime.datetime.now(),"##### CAM7 pts stream reset=",len(videoData))
            else:
                # valid video stream found
                break

        return videoData


    ####### CAM CAM CAM CAM new procedure
    # called when the refresh timeout occurs and the stream m3u8 file is updated
    def refreshStream(self, sid, station_list, pts):

        channelUri = self.local_locast.get_station_stream_uri(sid)
        print(datetime.datetime.now(),"Restarting ffmpeg")
        try:
            self.ffmpeg_proc.terminate()
            while True:
                if self.ffmpeg_proc.poll() == None:
                    print(datetime.datetime.now(),"##### CAM ffmpeg is alive")
                    time.sleep(0.01) # allow for other processes to run
                    self.ffmpeg_proc.terminate()
                else:
                    print(datetime.datetime.now(),"##### CAM ffmpeg is dead")
                    break


        except ValueError:
            pass

        print(datetime.datetime.now(),"Refresh Stream channelUri="+channelUri)
        
        if pts > 0:
            # currently not used copyts seems to work fine.
            ptsstr = print("='setpts=%d'"%(pts))
            ffmpeg_command = [self.config['main']['ffmpeg_path'],
                                "-i", channelUri,
                                "-c:v", "copy",
                                "-c:a", "copy",
                                "-f", "mpegts",
                                "-nostats", 
                                "-hide_banner",
                                "-loglevel", "warning",
                                "-metadata", "service_provider=Locast",  #CAM
                                "-metadata", "service_name="+self.setServiceName(station_list, sid),    #CAM
                                "-copyts",
                                "-vf", ptsstr,
                                "pipe:1"]
        else:
            ffmpeg_command = [self.config['main']['ffmpeg_path'],
                                "-i", channelUri,
                                "-c:v", "copy",
                                "-c:a", "copy",
                                "-f", "mpegts",
                                "-nostats", 
                                "-hide_banner",
                                "-loglevel", "warning",
                                "-metadata", "service_provider=Locast",  #CAM
                                "-metadata", "service_name="+self.setServiceName(station_list, sid),    #CAM
                                "-copyts",
                                "pipe:1"]
        return subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE)
        ###### CAM End of method

    ####### CAM CAM CAM CAM new procedure
    # returns the service name used to sync with the EPG channel name
    def setServiceName(self, station_list, sid):
        service_name = self.config['main']['servicename_prefix'] + \
            str(station_list[sid]['channel']) + \
            self.config['main']['servicename_suffix'] + \
            " " + station_list[sid]['friendlyName']  #CAM
        return service_name
        ###### CAM End of method
  
    
    

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

    print("Now listening for requests.")
    for i in range(int(config["main"]["concurrent_listeners"])):
        TVHeadendHttpServer(serverSocket, config, locast, location)

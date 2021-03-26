import os
import urllib
import copy
import time
import pathlib
import logging
from threading import Thread
import socket
import re
import mimetypes
import json
from http.server import HTTPServer
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import lib.tvheadend.stations as stations
import lib.tvheadend.utils as utils
import lib.tuner_interface
from lib.templates import templates
from lib.tvheadend.templates import tvh_templates
import lib.tvheadend.channels_m3u as channels_m3u
from lib.tvheadend.epg2xml import EPGLocast
from lib.tvheadend.user_config import TVHUserConfig
from lib.tvheadend.pages.configform_html import ConfigFormHTML
from lib.tvheadend.pages.index_js import IndexJS

MIN_TIME_BETWEEN_LOCAST = 0.4


class WebAdminHttpHandler(lib.tuner_interface.PlexHttpHandler):
    # class variables
    # Either None or the UDP target
    # defines when the UDP stream is terminated for each instance of the http server
    udp_server_status = []
    hdhr_station_scan = -1
    udp_socket = None
    config_obj = None
    config = None
    station_obj = None
    locast = None
    location = None
    hdhr_queue = None
    html_folders = ['web', 'emby', 'images', 'html', 'pages']

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
        self.server_instance = -1
        self.logger = logging.getLogger(__name__)
        super().__init__(*args)

    def log_message(self, format, *args):
        self.logger.debug('[%s] %s' % (self.address_string(), format%args))


    def do_GET(self):
        stream_url = self.config['main']['plex_accessible_ip'] + ':' + str(self.config['main']['plex_accessible_port'])
        web_admin_url = self.config['main']['plex_accessible_ip'] + ':' + str(self.config['main']['web_admin_port'])
        content_path = self.path
        valid_check = re.match(r'^(/([A-Za-z0-9\._\-]+)/[A-Za-z0-9\._\-/]+)[?%&A-Za-z0-9\._\-/=]*$', content_path)

        if content_path == '/':
            self.send_response(302)
            self.send_header('Location', 'web/index.html')
            self.end_headers()

        elif content_path == '/favicon.ico':
            self.send_response(302)
            self.send_header('Location', 'images/favicon.png')
            self.end_headers()

        elif content_path == '/discover.json':
            self.do_response(200,
                'application/json',
                tvh_templates['jsonDiscover'].format(self.config['main']['reporting_friendly_name'],
                    self.config['main']['reporting_model'],
                    self.config['main']['reporting_firmware_name'],
                    self.config['main']['reporting_firmware_ver'],
                    self.config['hdhomerun']['hdhr_id'],
                    self.config['main']['tuner_count'],
                    web_admin_url))

        elif content_path == '/device.xml':
            self.do_response(200,
                'application/xml',
                tvh_templates['xmlDevice'].format(self.config['main']['reporting_friendly_name'],
                    self.config['main']['reporting_model'],
                    self.config['hdhomerun']['hdhr_id'],
                    self.config['main']['uuid']
                ))

        elif content_path == '/lineup_status.json':
            if WebAdminHttpHandler.hdhr_station_scan < 0:
                return_json = tvh_templates['jsonLineupStatusIdle'] \
                    .replace("Antenna", self.config['main']['tuner_type'])
            else:
                WebAdminHttpHandler.hdhr_station_scan += 20
                if WebAdminHttpHandler.hdhr_station_scan > 100:
                    WebAdminHttpHandler.hdhr_station_scan = 100
                num_of_channels = len(WebAdminHttpHandler.station_obj.get_dma_stations_and_channels())
                return_json = tvh_templates['jsonLineupStatusScanning'].format(
                    WebAdminHttpHandler.hdhr_station_scan,
                    int(num_of_channels * WebAdminHttpHandler.hdhr_station_scan / 100))
                if WebAdminHttpHandler.hdhr_station_scan == 100:
                    WebAdminHttpHandler.hdhr_station_scan = -1
                    for index, scan_status in enumerate(WebAdminHttpHandler.rmg_station_scans):
                        if scan_status == 'Scan':
                            WebAdminHttpHandler.rmg_station_scans[index] = "Idle"
                            self.put_hdhr_queue(index, None, 'Idle')
            self.do_response(200, 'application/json', return_json)

        elif content_path == '/config.json':
            if self.config['main']['disable_web_config']:
                self.do_response(501, 'text/html', templates['htmlError']
                    .format('501 - Config pages disabled.'
                            ' Set [main][disable_web_config] to False in the config file to enable'))
            else:
                self.do_response(200, 'application/json', json.dumps(self.config_obj.filter_config_data()))

        elif content_path == '/channels.m3u':
            self.do_response(200, 'audio/x-mpegurl',
                channels_m3u.get_channels_m3u(self.config, stream_url))

        elif content_path == '/playlist':
            self.send_response(302)
            self.send_header('Location', '/channels.m3u')
            self.end_headers()

        elif content_path == '/lineup.json':
            station_list = WebAdminHttpHandler.station_obj.get_dma_stations_and_channels()
            return_json = ''
            for index, list_key in enumerate(station_list):
                if 'HD' in station_list[list_key]:
                    hd = ',\n    "HD": 1'
                else:
                    hd = ''

                sid = str(list_key)
                return_json = return_json + \
                              tvh_templates['jsonLineup'].format(
                        station_list[sid]['channel'],
                        station_list[sid]['friendlyName'],
                        stream_url + '/watch/' + sid,
                        hd)
                if len(station_list) != (index + 1):
                    return_json = return_json + ','
            return_json = "[" + return_json + "]"
            self.do_response(200, 'application/json', return_json)

        elif content_path == '/lineup.xml':  # must encode the strings
            station_list = WebAdminHttpHandler.station_obj.get_dma_stations_and_channels()
            return_xml = ''
            for list_key in station_list:
                if 'HD' in station_list[list_key]:
                    hd = '    <HD>1</HD>'
                else:
                    hd = ''

                sid = str(list_key)
                return_xml = return_xml + \
                             tvh_templates['xmlLineup'].format(
                        station_list[sid]['channel'],
                        escape(station_list[sid]['friendlyName']),
                        stream_url + '/watch/' + sid,
                        hd)
            return_xml = "<Lineup>" + return_xml + "</Lineup>"
            self.do_response(200, 'application/xml', return_xml)

        elif content_path == '/xmltv.xml':
            epg = EPGLocast(self.config, self.location)
            self.do_response(200, 'application/xml', epg.get_epg())

        elif content_path == '/pages/configform.html':
            configform = ConfigFormHTML()
            self.do_response(200, 'text/html', configform.get(self.config_obj.defn_json))

        elif content_path == '/pages/index.js':
            indexjs = IndexJS()
            self.do_response(200, 'text/javascript', indexjs.get(self.config))

        elif valid_check:
            if valid_check and valid_check.group(2) in WebAdminHttpHandler.html_folders:
                file_path = valid_check.group(1)
                htdocs_path = pathlib.Path(self.script_dir).joinpath('htdocs')
                fullfile_path = pathlib.Path(htdocs_path).joinpath(*file_path.split('/'))
                self.do_file_response(200, fullfile_path, content_path)
            else:
                self.logger.warning('Invalid content. ignoring {}'.format(content_path))
                self.do_response(501, 'text/html', templates['htmlError'].format('501 - Badly formed URL'))

        else:
            self.logger.info('UNKNOWN HTTP Request {}'.format(content_path))
            self.do_response(501, 'text/html', templates['htmlError'].format('501 - Not Implemented'))
            #super().do_GET()
        return

    def do_POST(self):
        content_path = self.path
        query_data = {}
        self.logger.debug('Receiving POST form {} {}'.format(content_path, query_data))
        # get POST data
        if self.headers.get('Content-Length') != '0':
            post_data = self.rfile.read(int(self.headers.get('Content-Length'))).decode('utf-8')
            # if an input is empty, then it will remove it from the list when the dict is gen
            query_data = urllib.parse.parse_qs(post_data)

        # get QUERYSTRING
        if self.path.find('?') != -1:
            content_path = self.path[0:self.path.find('?')]
            get_data = self.path[(self.path.find('?') + 1):]
            get_data_elements = get_data.split('&')
            for get_data_item in get_data_elements:
                get_data_item_split = get_data_item.split('=')
                if len(get_data_item_split) > 1:
                    query_data[get_data_item_split[0]] = get_data_item_split[1]

        if content_path == '/pages/configform.html':
            if self.config['main']['disable_web_config']:
                self.do_response(501, 'text/html', templates['htmlError']
                    .format('501 - Config pages disabled. '
                    'Set [main][disable_web_config] to False in the config file to enable'))
            else:
                # Take each key and make a [section][key] to store the value
                config_changes = {}
                for key in query_data:
                    key_pair = key.split('-')
                    if key_pair[0] not in config_changes:
                        config_changes[key_pair[0]] = {}
                    config_changes[key_pair[0]][key_pair[1]] = query_data[key]
                results = self.config_obj.update_config(config_changes)
                self.do_response(200, 'text/html', results)

        elif content_path == '/lineup.post':
            if query_data['scan'] == 'start':
                WebAdminHttpHandler.hdhr_station_scan = 0
                for index, scan_status in enumerate(WebAdminHttpHandler.rmg_station_scans):
                    if scan_status == 'Idle':
                        WebAdminHttpHandler.rmg_station_scans[index] = "Scan"
                        self.put_hdhr_queue(index, None, 'Scan')
                self.do_response(200, 'text/html')

                # putting this here after the response on purpose
                WebAdminHttpHandler.station_obj.refresh_dma_stations_and_channels()

            elif query_data['scan'] == 'abort':
                self.do_response(200, 'text/html')
                WebAdminHttpHandler.hdhr_station_scan = -1
                for index, scan_status in enumerate(WebAdminHttpHandler.rmg_station_scans):
                    if scan_status == 'Scan':
                        WebAdminHttpHandler.rmg_station_scans[index] = "Idle"
                        self.put_hdhr_queue(index, None, 'Idle')

            else:
                self.logger.warning("Unknown scan command " + query_data['scan'])
                self.do_response(400, 'text/html',
                    templates['htmlError'].format(
                        query_data['scan'] + ' is not a valid scan command'))
        elif content_path.startswith('/emby/Sessions/Capabilities/Full'):
                self.do_response(204, 'text/html')
        
        else:
            super().do_POST()
        return

    def do_file_response(self, code, reply_file, content_path):
        if reply_file:
            try:
                f = open(reply_file, 'rb')
                mime_lookup = mimetypes.guess_type(str(reply_file))
                self.send_response(code)
                self.send_header('Content-type', mime_lookup[0])
                self.end_headers()
                x = f.read()
                self.wfile.write(x)
                f.close()
            except IsADirectoryError as e:
                self.logger.info(e)
                self.do_response(401, 'text/html', templates['htmlError'].format('401 - Unauthorized'))
            except FileNotFoundError as e:
                self.logger.info(e)
                self.do_response(404, 'text/html', templates['htmlError'].format('404 - File Not Found'))
            except NotADirectoryError as e:
                self.logger.info(e)
                self.do_response(404, 'text/html', templates['htmlError'].format('404 - Folder Not Found'))

    def do_response(self, code, mime, reply_str=None):
        self.send_response(code)
        self.send_header('Content-type', mime)
        self.end_headers()
        if reply_str:
            try:
                self.wfile.write(reply_str.encode('utf-8'))
            except BrokenPipeError:
                self.logger.debug('Client dropped connection before results were sent, ignoring')

    def put_hdhr_queue(self, index, channel, status):
        if not self.config['hdhomerun']['disable_hdhr']:
            WebAdminHttpHandler.hdhr_queue.put(
                {'tuner': index, 'channel': channel, 'status': status})

class WebAdminHttpServer(Thread):

    def __init__(self, server_socket, config_object, locast_service, location, _hdhr_queue, _index):
        Thread.__init__(self)

        WebAdminHttpHandler.config_obj = config_object
        WebAdminHttpHandler.config = config_object.data

        self.bind_ip = config_object.data['main']['bind_ip']
        self.bind_port = config_object.data['main']['web_admin_port']

        stations.Stations.config = config_object.data
        stations.Stations.locast = locast_service
        stations.Stations.location = location
        WebAdminHttpHandler.station_obj = stations.Stations()
        WebAdminHttpHandler.locast = locast_service
        WebAdminHttpHandler.location = location
        WebAdminHttpHandler.hdhr_queue = _hdhr_queue

        # init station scans 
        tmp_rmg_scans = []
        for x in range(int(config_object.data['main']['tuner_count'])):
            tmp_rmg_scans.append('Idle')

        tmp_udp_status = []
        for x in range(int(config_object.data['main']['concurrent_listeners'])):
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

        WebAdminHttpHandler.rmg_station_scans = tmp_rmg_scans
        WebAdminHttpHandler.udp_server_status = tmp_udp_status
        WebAdminHttpHandler.udp_socket = tmp_udp_socket

        self.index = _index
        self.socket = server_socket
        self.start()

    def run(self):
        HttpHandlerClass = FactoryWebAdminHttpHandler(self.index)
        httpd = HTTPServer((self.bind_ip, self.bind_port), HttpHandlerClass, False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None
        httpd.serve_forever()


def FactoryWebAdminHttpHandler(index):
    class CustomWebAdminHttpHandler(WebAdminHttpHandler):
        def __init__(self, *args, **kwargs):
            super(CustomWebAdminHttpHandler, self).__init__(*args, **kwargs)
    return CustomWebAdminHttpHandler


def start(config, locast, location, hdhr_queue):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    config_copy = copy.deepcopy(config)
    config_obj = TVHUserConfig(config=config_copy)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config_obj.data['main']['bind_ip'], config_obj.data['main']['web_admin_port']))
    server_socket.listen(int(config_obj.data['main']['concurrent_listeners']))
    logger = logging.getLogger(__name__)
    logger.debug('Now listening for requests. Number of listeners={}'.format(config_obj.data['main']['concurrent_listeners']))
    for i in range(int(config_obj.data['main']['concurrent_listeners'])):
        WebAdminHttpServer(server_socket, config_obj, locast, location, hdhr_queue, i)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
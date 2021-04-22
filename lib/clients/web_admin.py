'''
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
'''

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
import random
import importlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import lib.tvheadend.utils as utils
import lib.clients.channels as channels
from lib.clients.epg2xml import EPG

from lib.tvheadend.templates import tvh_templates
from lib.config.user_config import TVHUserConfig
from lib.web.pages.configform_html import ConfigFormHTML
from lib.web.pages.index_js import IndexJS
from lib.config.config_defn import ConfigDefn
from lib.db.db_plugins import DBPlugins

MIN_TIME_BETWEEN_LOCAST = 0.4


class WebAdminHttpHandler(BaseHTTPRequestHandler):
    # class variables
    # Either None or the UDP target
    # defines when the UDP stream is terminated for each instance of the http server
    hdhr_station_scan = -1
    plugins = None
    namespace_list = None
    config = None
    hdhr_queue = None
    rmg_station_scans = []
    logger = None

    def __init__(self, *args):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
        try:
            super().__init__(*args)
        except ConnectionResetError:
            self.logger.warning('########## ConnectionResetError occurred')
            time.sleep(1)
            super().__init__(*args)

    def log_message(self, _format, *args):
        self.logger.debug('[%s] %s' % (self.address_string(), _format % args))

    def do_GET(self):

        stream_url = self.config['main']['plex_accessible_ip'] + ':' + str(self.config['main']['plex_accessible_port'])
        web_admin_url = self.config['main']['plex_accessible_ip'] + ':' + str(self.config['main']['web_admin_port'])
        valid_check = re.match(r'^(/([A-Za-z0-9\._\-]+)/[A-Za-z0-9\._\-/]+)[?%&A-Za-z0-9\._\-/=]*$', self.path)
        content_path, query_data = self.get_query_data()

        if content_path == '/':
            self.send_response(302)
            self.send_header('Location', 'html/index.html')
            self.end_headers()

        elif content_path == '/favicon.ico':
            self.send_response(302)
            self.send_header('Location', 'images/favicon.png')
            self.end_headers()

        elif content_path == '/discover.json':
            ns_inst_path = self.get_ns_inst_path(query_data)
            self.do_response(200,
                'application/json',
                tvh_templates['jsonDiscover'].format(
                    self.config['main']['reporting_friendly_name'],
                    self.config['main']['reporting_model'],
                    self.config['main']['reporting_firmware_name'],
                    self.config['main']['reporting_firmware_ver'],
                    self.config['hdhomerun']['hdhr_id'],
                    self.config['main']['tuner_count'],
                    web_admin_url, ns_inst_path))

        elif content_path == '/device.xml':
            self.do_response(200,
                'application/xml',
                tvh_templates['xmlDevice'].format(self.config['main']['reporting_friendly_name'],
                    self.config['main']['reporting_model'],
                    self.config['hdhomerun']['hdhr_id'],
                    self.config['main']['uuid']
                ))

        # TBD NEED TO WORK ON THIS TO FIX FOR PLEX SCAN
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
                self.do_response(501, 'text/html', tvh_templates['htmlError']
                    .format('501 - Config pages disabled.'
                            ' Set [main][disable_web_config] to False in the config file to enable'))
            else:
                self.do_response(200, 'application/json', json.dumps(self.plugins.config_obj.filter_config_data()))

        elif content_path == '/channels.m3u':
            self.do_response(200, 'audio/x-mpegurl',
                channels.get_channels_m3u(self.config, stream_url, query_data['name'], query_data['instance']))

        elif content_path == '/playlist':
            self.send_response(302)
            self.send_header('Location', self.path.replace('playlist','channels.m3u'))
            self.end_headers()

        elif content_path == '/lineup.json':
            self.do_response(200, 'application/json', channels.get_channels_json(self.config, stream_url, query_data['name'], query_data['instance']))

        elif content_path == '/lineup.xml':  # must encode the strings
            self.do_response(200, 'application/xml', channels.get_channels_xml(self.config, stream_url, query_data['name'], query_data['instance']))

        elif content_path == '/xmltv.xml':
            epg = EPG(self.plugins, query_data['name'], query_data['instance'])
            reply_str = epg.get_epg_xml()
            self.do_response(200, 'application/xml', reply_str)

        elif content_path == '/pages/configform.html' and 'area' in query_data:
            configform = ConfigFormHTML()
            form = configform.get(self.plugins.config_obj.defn_json.get_defn(query_data['area']), query_data['area'])
            self.do_response(200, 'text/html', form)

        elif content_path == '/pages/index.js':
            indexjs = IndexJS()
            self.do_response(200, 'text/javascript', indexjs.get(self.config))

        elif content_path == '/background':
            self.send_random_image()

        elif valid_check:
            if valid_check:
                file_path = valid_check.group(1)
                htdocs_path = self.config["paths"]["www_pkg"]
                path_list = file_path.split('/')
                fullfile_path = htdocs_path + '.'.join(path_list[:-1])
                self.do_file_response(200, fullfile_path, path_list[-1])
            else:
                self.logger.warning('Invalid content. ignoring {}'.format(content_path))
                self.do_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Badly formed URL'))

        else:
            self.logger.info('UNKNOWN HTTP Request {}'.format(content_path))
            self.do_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Not Implemented'))
            # super().do_GET()
        return


    def do_POST(self):
        content_path = self.path
        query_data = {}
        self.logger.debug('Receiving POST form {} {}'.format(content_path, query_data))
        # get POST data
        if self.headers.get('Content-Length') != '0':
            post_data = self.rfile.read(int(self.headers.get('Content-Length'))).decode('utf-8')
            # if an input is empty, then it will remove it from the list when the dict is gen
            query_data = urllib.parse.parse_qs(post_data, keep_blank_values=True)
            for key, value in query_data.items():
                if value[0] == '':
                    value[0] = None

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
                self.do_response(501, 'text/html', tvh_templates['htmlError']
                    .format('501 - Config pages disabled. '
                            'Set [main][disable_web_config] to False in the config file to enable'))
            else:
                # Take each key and make a [section][key] to store the value
                config_changes = {}
                area = query_data['area'][0]
                del query_data['area']
                for key in query_data:
                    key_pair = key.split('-')
                    if key_pair[0] not in config_changes:
                        config_changes[key_pair[0]] = {}
                    config_changes[key_pair[0]][key_pair[1]] = query_data[key]
                results = self.plugins.config_obj.update_config(area, config_changes)
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
                    tvh_templates['htmlError'].format(
                        query_data['scan'] + ' is not a valid scan command'))
        elif content_path.startswith('/emby/Sessions/Capabilities/Full'):
            self.do_response(204, 'text/html')

        else:
            super().do_POST()
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
            namespace = None
            instance = None
            for ns in WebAdminHttpHandler.namespace_list:
                if path_list[1].lower() == ns.lower():
                    namespace = ns
                    del path_list[1]
                    instance_list = WebAdminHttpHandler.namespace_list[namespace]
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


    def do_file_response(self, code, package, reply_file):
        if reply_file:
            try:
                x = importlib.resources.read_binary(package, reply_file)
                mime_lookup = mimetypes.guess_type(reply_file)
                self.send_response(code)
                self.send_header('Content-type', mime_lookup[0])
                self.end_headers()
                self.wfile.write(x)
            except IsADirectoryError as e:
                self.logger.info(e)
                self.do_response(401, 'text/html', tvh_templates['htmlError'].format('401 - Unauthorized'))
            except FileNotFoundError as e:
                self.logger.info(e)
                self.do_response(404, 'text/html', tvh_templates['htmlError'].format('404 - File Not Found'))
            except NotADirectoryError as e:
                self.logger.info(e)
                self.do_response(404, 'text/html', tvh_templates['htmlError'].format('404 - Folder Not Found'))
            except ConnectionAbortedError as e:
                self.logger.info(e)
            except ModuleNotFoundError as e:
                self.logger.info(e)
                self.do_response(404, 'text/html', tvh_templates['htmlError'].format('404 - Area Not Found'))

    def do_response(self, code, mime, reply_str=None):
        self.send_response(code)
        self.send_header('Content-type', mime)
        self.end_headers()
        if reply_str:
            try:
                self.wfile.write(reply_str.encode('utf-8'))
            except BrokenPipeError:
                self.logger.debug('Client dropped connection before results were sent, ignoring')

    def get_ns_inst_path(self, _query_data):
        if _query_data['name']:
            path = '/'+_query_data['name']
        else:
            path = ''
        if _query_data['instance']:
            path += '/'+_query_data['instance']
        return path

    def send_random_image(self):
        if not self.config['display']['backgrounds']:
            background_dir = self.config['paths']['themes_pkg'] + '.' + \
                             self.config['display']['theme']
            image_list = list(importlib.resources.contents(background_dir))
            image_found = False
            while not image_found:
                image = random.choice(image_list)
                mime_lookup = mimetypes.guess_type(image)
                if mime_lookup[0] is not None and \
                        mime_lookup[0].startswith('image'):
                    image_found = True
            self.do_file_response(200, background_dir, image)

        else:
            background = self.config['display']['backgrounds']
            try:
                image_found = False
                count = 0
                while not image_found:
                    image = random.choice(os.listdir(background))
                    full_image_path = pathlib.Path(background).joinpath(image)
                    mime_lookup = mimetypes.guess_type(str(full_image_path))
                    if mime_lookup[0].startswith('image'):
                        image_found = True
                    else:
                        count += 1
                        if count > 5:
                            self.logger.debug('Image not found at {}'.format(background))
                            self.do_response(404, 'text/html',
                                tvh_templates['htmlError'].format('404 - Background Image Not Found'))
                            return
                self.do_file_response(200, full_image_path)
            except FileNotFoundError:
                self.logger.warning('Background Theme Folder not found')
                self.do_response(404, 'text/html', tvh_templates['htmlError'].format('404 - Background Folder Not Found'))

    def put_hdhr_queue(self, index, channel, status):
        if not self.config['hdhomerun']['disable_hdhr']:
            WebAdminHttpHandler.hdhr_queue.put(
                {'tuner': index, 'channel': channel, 'status': status})


class WebAdminHttpServer(Thread):

    def __init__(self, server_socket, _plugins):
        Thread.__init__(self)
        self.bind_ip = _plugins.config_obj.data['main']['bind_ip']
        self.bind_port = _plugins.config_obj.data['main']['web_admin_port']
        self.socket = server_socket
        self.start()

    def run(self):
        HttpHandlerClass = FactoryWebAdminHttpHandler()
        httpd = HTTPServer((self.bind_ip, self.bind_port), HttpHandlerClass, False)
        httpd.socket = self.socket
        httpd.server_bind = self.server_close = lambda self: None
        httpd.serve_forever()


def FactoryWebAdminHttpHandler():
    class CustomWebAdminHttpHandler(WebAdminHttpHandler):
        def __init__(self, *args, **kwargs):
            super(CustomWebAdminHttpHandler, self).__init__(*args, **kwargs)
    return CustomWebAdminHttpHandler

def init_class_var(_plugins, _hdhr_queue):
    WebAdminHttpHandler.logger = logging.getLogger(__name__)
    WebAdminHttpHandler.plugins = _plugins
    WebAdminHttpHandler.config = _plugins.config_obj.data
    WebAdminHttpHandler.hdhr_queue = _hdhr_queue
    if not _plugins.config_obj.defn_json:
        _plugins.config_obj.defn_json = ConfigDefn(_config=_plugins.config_obj.data)

    plugins_db = DBPlugins(_plugins.config_obj.data)
    WebAdminHttpHandler.namespace_list = plugins_db.get_instances()

    tmp_rmg_scans = []
    for x in range(int(_plugins.config_obj.data['main']['tuner_count'])):
        tmp_rmg_scans.append('Idle')
    WebAdminHttpHandler.rmg_station_scans = tmp_rmg_scans


def start(_plugins, _hdhr_queue):
    """
    main starting point for all classes and services in this file.  
    Called from main.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((_plugins.config_obj.data['main']['bind_ip'], _plugins.config_obj.data['main']['web_admin_port']))
    server_socket.listen(int(_plugins.config_obj.data['main']['concurrent_listeners']))
    utils.logging_setup(_plugins.config_obj.data['paths']['config_file'])
    logger = logging.getLogger(__name__)
    logger.debug(
        'Now listening for requests. Number of listeners={}'.format(_plugins.config_obj.data['main']['concurrent_listeners']))
    init_class_var(_plugins, _hdhr_queue)
    for i in range(int(_plugins.config_obj.data['main']['concurrent_listeners'])):
        WebAdminHttpServer(server_socket, _plugins)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass

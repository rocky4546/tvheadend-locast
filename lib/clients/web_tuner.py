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
from lib.db.db_config_defn import DBConfigDefn
from lib.streams.m3u8_redirect import M3U8Redirect
from lib.streams.internal_proxy import InternalProxy
from lib.streams.ffmpeg_proxy import FFMpegProxy


class TunerHttpHandler(BaseHTTPRequestHandler):
    # class variables
    plugins = None
    namespace_list = None
    hdhr_queue = None
    config = None
    rmg_station_scans = []
    logger = None
    channels_db = None

    def __init__(self, *args):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
        self.ffmpeg_proc = None  # process for running ffmpeg
        self.block_moving_avg = 0
        self.last_refresh = None
        self.block_prev_pts = 0
        self.block_prev_time = None
        self.buffer_prev_time = None
        self.block_max_pts = 0
        self.small_pkt_streaming = False
        self.real_namespace = None
        self.real_instance = None
        self.m3u8_redirect = M3U8Redirect(TunerHttpHandler.plugins, TunerHttpHandler.hdhr_queue)
        self.internal_proxy = InternalProxy(TunerHttpHandler.plugins, TunerHttpHandler.hdhr_queue)
        self.ffmpeg_proxy = FFMpegProxy(TunerHttpHandler.plugins, TunerHttpHandler.hdhr_queue)
        self.db_configdefn = DBConfigDefn(self.config)
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

    def do_tuning(self, sid, _namespace, _instance):
        # refresh the config data in case it changed in the web_admin process
        self.config = self.db_configdefn.get_config()
        self.plugins.config_obj.data = self.config
        try:
            station_list = TunerHttpHandler.channels_db.get_channels(_namespace, _instance)
            self.real_namespace = station_list[sid]['namespace']
            self.real_instance = station_list[sid]['instance']
        except KeyError:
            self.logger.warning('Unknown channel id {}'.format(sid))
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown channel'))
            return
        if self.config[self.real_namespace.lower()]['player-stream_type'] == 'm3u8redirect':
            self.do_dict_response(self.m3u8_redirect.gen_response(station_list[sid]))
            return
        elif self.config[self.real_namespace.lower()]['player-stream_type'] == 'internalproxy':
            resp = self.internal_proxy.gen_response(station_list[sid]['number'], TunerHttpHandler)
            self.do_dict_response(resp)
            if resp['tuner'] < 0:
                return
            else:
                self.internal_proxy.stream_direct(station_list[sid], self.wfile)
        elif self.config[self.real_namespace.lower()]['player-stream_type'] == 'ffmpegproxy':
            resp = self.ffmpeg_proxy.gen_response(station_list[sid]['number'], TunerHttpHandler)
            self.do_dict_response(resp)
            if resp['tuner'] < 0:
                return
            else:
                self.ffmpeg_proxy.stream_ffmpeg(station_list[sid], self.wfile)
        else:
            self.do_mime_response(501, 'text/html', tvh_templates['htmlError'].format('501 - Unknown streamtype'))
            self.logger.error('Unknown [player-stream_type] {}'
                .format(self.config[self.real_namespace.lower()]['player-stream_type']))
            return
        self.logger.info('1 Locast Connection Closed')
        TunerHttpHandler.rmg_station_scans[resp['tuner']] = 'Idle'



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

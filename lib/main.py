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

import argparse
import logging
import platform
import sys
import time
from multiprocessing import Queue, Process

import lib.clients.hdhr.hdhr_server as hdhr_server
import lib.clients.web_tuner as web_tuner
import lib.clients.web_admin as web_admin
import lib.common.utils as utils
import lib.plugins.plugin_handler as plugin_handler
import lib.clients.ssdp.ssdp_server as ssdp_server
from lib.common.utils import clean_exit
from lib.common.pickling import Pickling


try:
    import pip
except ModuleNotFoundError:
    print('Unable to load pip module to install upgrades')

try:
    import cryptography
except ImportError:
    # pip.main(['install', 'cryptography'])
    print('Unable to load cryptography module, will not encrypt passwords')

import lib.config.user_config as user_config

if sys.version_info.major == 2 or sys.version_info < (3, 7):
    print('Error: cabernet requires python 3.7+.')
    sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(description='Fetch online streams', epilog='')
    parser.add_argument('--config_file', dest='cfg', type=str, default=None, help='')
    return parser.parse_args()


def main(script_dir):
    """ main startup method for app """
    hdhr_serverx = None
    ssdp_serverx = None
    webadmin = None
    tuner = None

    # Gather args
    args = get_args()

    # Get Operating system
    opersystem = platform.system()

    # Open Configuration File
    config_obj = user_config.get_config(script_dir, opersystem, args)
    config = config_obj.data
    logger = logging.getLogger(__name__)

    logger.warning('MIT License, Copyright (C) 2021 ROCKY4546')
    logger.info('Initiating Cabernet v' + utils.get_version_str())

    logger.info('Getting Plugins...')
    plugins = plugin_handler.PluginHandler(config_obj)
    plugins.initialize_plugins()
    config_obj.defn_json = None
    plugins.refresh_channels()

    if opersystem in ['Windows']:
        pickle_it = Pickling(config)
        pickle_it.to_pickle(plugins)

    try:
        hdhr_queue = Queue()
        logger.info('Starting admin website on {}:{}'.format(
            config['web']['plex_accessible_ip'],
            config['web']['web_admin_port']))
        webadmin = Process(target=web_admin.start, args=(plugins, hdhr_queue,))
        webadmin.start()
        time.sleep(0.1)

        logger.info('Starting streaming tuner website on {}:{}'.format(
            config['web']['plex_accessible_ip'],
            config['web']['plex_accessible_port']))
        tuner = Process(target=web_tuner.start, args=(plugins, hdhr_queue,))
        tuner.start()
        time.sleep(0.1)

        logger.info('Refreshing EPG data')
        plugins.refresh_epg()
        time.sleep(0.1)
        
        if not config['ssdp']['disable_ssdp']:
            logger.info('Starting SSDP service on port 1900')
            ssdp_serverx = Process(target=ssdp_server.ssdp_process, args=(config,))
            ssdp_serverx.daemon = True
            ssdp_serverx.start()

        if not config['hdhomerun']['disable_hdhr']:
            logger.info('Starting HDHR service on port 65001')
            hdhr_serverx = Process(target=hdhr_server.hdhr_process, args=(config, hdhr_queue,))
            hdhr_serverx.start()
        # Let the other process and threads take turns to run
        time.sleep(0.1)

        if opersystem in ['Windows']:
            time.sleep(2)
            pickle_it.delete_pickle(plugins.__class__.__name__)
        logger.info('Cabernet is now online.')

        # wait forever
        while True:
            time.sleep(3600)

    except KeyboardInterrupt:
        logger.info('^C received, shutting down the server')
        shutdown(config, hdhr_serverx, ssdp_serverx, webadmin, tuner, config_obj)


def shutdown(_config, _hdhr_serverx, _ssdp_serverx, _webadmin, _tuner, _config_obj):
    if not _config['hdhomerun']['disable_hdhr'] and _hdhr_serverx:
        _hdhr_serverx.terminate()
        _hdhr_serverx.join()
    if not _config['ssdp']['disable_ssdp'] and _ssdp_serverx:
        _ssdp_serverx.terminate()
        _ssdp_serverx.join()
    if _webadmin:
        _webadmin.terminate()
        _webadmin.join()
    if _tuner:
        _tuner.terminate()
        _tuner.join()
    if _config_obj and _config_obj.defn_json:
        _config_obj.defn_json.terminate()
    clean_exit()

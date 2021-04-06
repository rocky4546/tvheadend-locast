import sys
import time
import platform 
import argparse
import logging
from threading import Thread
from multiprocessing import Queue, Process

import lib.tvheadend.locast_service as locast_service
import lib.tvheadend.ssdp_server as ssdp_server
import lib.tvheadend.tuner_interface as tuner_interface
import lib.tvheadend.web_admin as web_admin
import lib.tvheadend.stations as stations 
import lib.location as location
import lib.tvheadend.utils as utils
import lib.tvheadend.epg2xml as epg2xml
import lib.tvheadend.hdhr_server as hdhr_server
from lib.l2p_tools import clean_exit

try:
    import pip
except ModuleNotFoundError:
    print('Unable to load pip module to install upgrades')

try:
    import cryptography
except ImportError:
    # pip.main(['install', 'cryptography'])
    print('Unable to load cryptography module, will not encrypt passwords')
    

import lib.tvheadend.user_config as user_config


if sys.version_info.major == 2 or sys.version_info < (3, 6):
    print('Error: Locast2Plex requires python 3.6+.')
    sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(description='Fetch TV from locast.', epilog='')
    parser.add_argument('--config_file', dest='cfg', type=str, default=None, help='')
    return parser.parse_args()


def main(script_dir):

    """ main startup method for app """
    
    # Gather args
    args = get_args()

    # Get Operating system
    opersystem = platform.system()

    # Open Configuration File
    config_obj = user_config.get_config(script_dir, opersystem, args)
    config = config_obj.data
    logger = logging.getLogger(__name__)
    if config['main']['locast_password'] == 'UNKNOWN':
        logger.critical("No password available.  Terminating process")
        clean_exit(1)

    logger.info('Initiating TVHeadend-Locast v' + utils.get_version_str())
    if config['main']['quiet_print']:
        utils.block_print()
    location_info = location.DMAFinder(config)
    if config['main']['quiet_print']:
        utils.enable_print()
    logger.debug('Location={}'.format(location_info.location['city']))

    locast = locast_service.TVHLocastService(location_info.location, config)

    if config['main']['quiet_print']:
        utils.block_print()
    # if past logins were invalid, do not keep trying
    if config['main']['login_invalid'] is not None:
        logger.error('Unable to login due to invalid logins.  Clear config entry login_invalid to try again')
        clean_exit(1)

    if not locast.login(config['main']['locast_username'], config['main']['locast_password']):
        if config['main']['quiet_print']:
            utils.enable_print()
        logger.error('Invalid Locast Login Credentials. Exiting...')
        # set the config file to know we have had a login failure
        current_time = str(int(time.time()))
        config_obj.write('main', 'login_invalid', current_time)
        clean_exit(1)
    if config['main']['quiet_print']:
        utils.enable_print()
    if not locast.validate_user():
        logger.error('2. Invalid Locast Login Credentials. Exiting...')
        clean_exit(1)

    try:
        logger.info('Starting Stations thread...')
        stations_server = Thread(target=stations.stations_process, args=(config, locast, location_info.location,))
        #stations_server.daemon = True
        stations_server.start()
        while not stations.check_station_file(config, location_info.location):
            time.sleep(1)

        hdhr_queue = Queue()
        logger.info('Starting admin website on {}:{}'.format(
            config['main']['plex_accessible_ip'],
            config['main']['web_admin_port']))
        webadmin = Process(target=web_admin.start, args=(config, locast, 
            location_info.location, hdhr_queue,))
        webadmin.start()
        time.sleep(0.1)

        logger.info('Starting streaming tuner website on {}:{}'.format(
            config['main']['plex_accessible_ip'],
            config['main']['plex_accessible_port']))
        tuner = Process(target=tuner_interface.start, args=(config, locast, 
            location_info.location, hdhr_queue,))
        tuner.start()
        time.sleep(0.1)

        if not config['main']['disable_ssdp']:
            logger.info('Starting SSDP service on port 1900')
            ssdp_serverx = Process(target=ssdp_server.ssdp_process, args=(config,))
            ssdp_serverx.daemon = True
            ssdp_serverx.start()

        logger.info('Starting EPG process...')
        epg_server = Thread(target=epg2xml.epg_process, args=(config, location_info.location,))
        #epg_server.daemon = True
        epg_server.start()
        time.sleep(0.1)

        # START HDHOMERUN
        if not config['hdhomerun']['disable_hdhr']:
            logger.info('Starting HDHR service on port 65001')
            hdhr_serverx = Process(target=hdhr_server.hdhr_process, args=(config, hdhr_queue,))
            hdhr_serverx.start()
        # Let the other process and threads take turns to run
        time.sleep(0.1)

        logger.info('TVHeadend_Locast is now online.')

        # wait forever
        while True:
            time.sleep(3600)

    except KeyboardInterrupt:
        logger.info('^C received, shutting down the server')
        if not config['hdhomerun']['disable_hdhr']:
            hdhr_serverx.terminate()
            hdhr_serverx.join()
        if not config['main']['disable_ssdp']:
            ssdp_serverx.terminate()
            ssdp_serverx.join()
        webadmin.terminate()
        webadmin.join()
        tuner.terminate()
        tuner.join()
        clean_exit()

# pylama:ignore=E722,E303,E302,E305
import os
import sys
import time
import platform 
import argparse
import pathlib
import logging
from multiprocessing import Process

import lib.tvheadend.locast_service as locast_service
import lib.ssdp_server as ssdp_server
import lib.tvheadend.tuner_interface as tuner_interface
import lib.epg2xml as epg2xml
import lib.stations as stations 
import lib.location as location
import lib.tvheadend.user_config as user_config
import lib.tvheadend.utils as utils
from lib.tvheadend.user_config import get_config
from lib.l2p_tools import clean_exit


if sys.version_info.major == 2 or sys.version_info < (3, 6):
    print('Error: Locast2Plex requires python 3.6+.')
    sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(description='Fetch TV from locast.', epilog='')
    parser.add_argument('--config_file', dest='cfg', type=str, default=None, help='')
    return parser.parse_args()


def main(script_dir):
    """ main startup method for app """
    utils.block_print()  # stop locast2plex logging until the logging engine is update
    
    # Gather args
    args = get_args()

    # Get Operating system
    opersystem = platform.system()

    # Open Configuration File
    configObj = get_config(script_dir, opersystem, args)
    config = configObj.data
    config["main"]["quiet"] = utils.str2bool(config["main"]["quiet"])
    
    # if requested, stop all the print statements in locast2plex
    # from printing to standard out
    if config["main"]["quiet"]:
        utils.block_print()
    else:
        utils.enable_print()

    # setup global logging
    utils.logging_setup(configObj.config_file)
    logging.info("Initiating TVHeadend-Locast v" + utils.get_version_str())
    
    if config["main"]["quiet_print"]:
        utils.block_print()
    location_info = location.DMAFinder(config)
    if config["main"]["quiet_print"]:
        utils.enable_print()
    logging.debug("Location={}".format(location_info.location['city']))

    locast = locast_service.LocastService(location_info.location, config)


    if config["main"]["quiet_print"]:
        utils.block_print()
    if not locast.login(config["main"]["locast_username"], config["main"]["locast_password"]):
        if config["main"]["quiet_print"]:
            utils.enable_print()
        logging.error("Invalid Locast Login Credentials. Exiting...")
        clean_exit(1)
    if config["main"]["quiet_print"]:
        utils.enable_print()
    if not locast.validate_user():
        logging.error("Invalid Locast Login Credentials. Exiting...")
        clean_exit(1)


    try:
        fcc_cache_dir = pathlib.Path(config["main"]["cache_dir"]).joinpath("stations")
        if not fcc_cache_dir.is_dir():
            fcc_cache_dir.mkdir()

        logging.debug("Starting First time Stations refresh...")
        if config["main"]["quiet_print"]:
            utils.block_print()
        stations.refresh_dma_stations_and_channels(config, locast, location_info.location)
        if config["main"]["quiet_print"]:
            utils.enable_print()

        logging.debug("Starting Stations thread...")
        if config["main"]["quiet_print"]:
            utils.block_print()
        stations_server = Process(target=stations.stations_process, args=(config, locast, location_info.location))
        stations_server.daemon = True
        stations_server.start()
        if config["main"]["quiet_print"]:
            utils.enable_print()

        logging.debug("Starting device server on " + config["main"]['plex_accessible_ip'] + ":" + config["main"]['plex_accessible_port'])
        tuner_interface.start(config, locast, location_info.location)

        if not config['main']['disable_ssdp']:
            logging.debug("Starting SSDP server...")
            if config["main"]["quiet_print"]:
                utils.block_print()
            ssdp_serverx = Process(target=ssdp_server.ssdp_process, args=(config,))
            ssdp_serverx.daemon = True
            ssdp_serverx.start()
            if config["main"]["quiet_print"]:
                utils.enable_print()

        logging.debug("Starting First time EPG refresh...")
        
        logging.debug("Starting EPG thread...")
        if config["main"]["quiet_print"]:
            utils.block_print()
        epg2xml.generate_epg_file(config, location_info.location)
        epg_server = Process(target=epg2xml.epg_process, args=(config, location_info.location))
        epg_server.daemon = True
        epg_server.start()
        if config["main"]["quiet_print"]:
            utils.enable_print()

        logging.info("TVHeadend_Locast is now online.")

        # wait forever
        while True:
            time.sleep(3600)

    except KeyboardInterrupt:
        logging.info('^C received, shutting down the server')
        ssdp_serverx.terminate()
        clean_exit()

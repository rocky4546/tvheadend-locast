# pylama:ignore=E722,E303,E302,E305
import os
import sys
import time
import platform 
import argparse
import pathlib
from multiprocessing import Process

import lib.tvheadend.locast_service as locast_service
import lib.ssdp_server as ssdp_server
import lib.tvheadend.tuner_interface as tuner_interface
import lib.epg2xml as epg2xml
import lib.stations as stations 
import lib.location as location
from lib.tvheadend.user_config import get_config
from lib.l2p_tools import clean_exit
from lib.tvheadend.utils import get_version_str


if sys.version_info.major == 2 or sys.version_info < (3, 6):
    print('Error: Locast2Plex requires python 3.6+.')
    sys.exit(1)


def get_args():
    parser = argparse.ArgumentParser(description='Fetch TV from locast.', epilog='')
    parser.add_argument('--config_file', dest='cfg', type=str, default=None, help='')
    return parser.parse_args()


def main(script_dir):
    """ main startup method for app """

    print("Initiating Locast2Plex v" + get_version_str())

    # Gather args
    args = get_args()

    # Get Operating system
    opersystem = platform.system()

    # set to directory of script
    print("script_dir=", script_dir)

    # Open Configuration File
    print("Opening and Verifying Configuration File.")
    config = get_config(script_dir, opersystem, args)
    print("config=", config)

    print("Getting user location...")
    location_info = location.DMAFinder(config)
    print("location_info=", location_info)

    locast = locast_service.LocastService(location_info.location, config) #CAM added config to class

    if (not locast.login(config["main"]["locast_username"], config["main"]["locast_password"])) or (not locast.validate_user()):
        print("Invalid Locast Login Credentials. Exiting...")
        clean_exit(1)


    try:
        fcc_cache_dir = pathlib.Path(config["main"]["cache_dir"]).joinpath("stations")
        if not fcc_cache_dir.is_dir():
            fcc_cache_dir.mkdir()

        print("Starting First time Stations refresh...")
        stations.refresh_dma_stations_and_channels(config, locast, location_info.location)

        print("Starting Stations thread...")
        stations_server = Process(target=stations.stations_process, args=(config, locast, location_info.location))
        stations_server.daemon = True
        stations_server.start()

        print("Starting device server on " + config["main"]['plex_accessible_ip'] + ":" + config["main"]['plex_accessible_port'])
        tuner_interface.start(config, locast, location_info.location)

        if not config['main']['disable_ssdp']:
            print("Starting SSDP server...")
            ssdp_serverx = Process(target=ssdp_server.ssdp_process, args=(config,))
            ssdp_serverx.daemon = True
            ssdp_serverx.start()

        print("Starting First time EPG refresh...")
        epg2xml.generate_epg_file(config, location_info.location)

        print("Starting EPG thread...")
        epg_server = Process(target=epg2xml.epg_process, args=(config, location_info.location))
        epg_server.daemon = True
        epg_server.start()

        print("TVHeadend_Locast is now online.")

        # wait forever
        while True:
            time.sleep(3600)

    except KeyboardInterrupt:
        print('^C received, shutting down the server')
        ssdp_serverx.terminate()
        clean_exit()

# pylama:ignore=E722,E303
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import pathlib
import logging
from datetime import datetime

import lib.m3u8 as m3u8
import lib.stations as stations
import lib.locast_service
from lib.l2p_tools import handle_url_except



class LocastService( lib.locast_service.LocastService ):

    config = None  #CAM

    def __init__(self, location, config):  #CAM
        super().__init__(location)
        self.config = config  #CAM


    @handle_url_except
    def validate_user(self):
        logging.debug('Validating User Info...')

        # get user info and make sure we donated
        userReq = urllib.request.Request('https://api.locastnet.org/api/user/me',
                                         headers={'Content-Type': 'application/json',
                                                  'authorization': 'Bearer ' + self.current_token,
                                                  'User-agent': self.DEFAULT_USER_AGENT})

        userOpn = urllib.request.urlopen(userReq)
        userRes = json.load(userOpn)
        userOpn.close()

        logging.debug('User didDonate: {}'.format(userRes['didDonate']))
        # Check if the user has donated, and we got an actual expiration date.
        if userRes['didDonate'] and userRes['donationExpire']: 
            donateExp = datetime.fromtimestamp(userRes['donationExpire'] / 1000)
            logging.debug('User donationExpire: {}'.format(donateExp))
            if datetime.now() > donateExp:
                logging.info("User's donation ad-free period has expired.")
                self.config['freeaccount']['is_free_account'] = True
            else:
                logging.info('User has an active subscription.')
                self.config['freeaccount']['is_free_account'] = False
        else:
            logging.info('User is a free account.')
            self.config['freeaccount']['is_free_account'] = True
        return True


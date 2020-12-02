# pylama:ignore=E722,E303
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import pathlib
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
        print("Validating User Info...")

        # get user info and make sure we donated
        userReq = urllib.request.Request('https://api.locastnet.org/api/user/me',
                                         headers={'Content-Type': 'application/json',
                                                  'authorization': 'Bearer ' + self.current_token,
                                                  'User-agent': self.DEFAULT_USER_AGENT})

        userOpn = urllib.request.urlopen(userReq)
        userRes = json.load(userOpn)
        userOpn.close()

        print("User Info obtained.")
        print("User didDonate: {}".format(userRes['didDonate']))
        # Check if the user has donated, and we got an actual expiration date.
        if userRes['didDonate'] and userRes['donationExpire']: 
        # Check if donation has expired.
            donateExp = datetime.fromtimestamp(userRes['donationExpire'] / 1000)
            print("User donationExpire: {}".format(donateExp))
            if datetime.now() > donateExp:
                print("User's donation ad-free period has expired.")
                self.config['main']['is_free_account'] = True #CAM
#CAM                return False
            else:  #CAM not a free account
                self.config['main']['is_free_account'] = False #CAM
        else:
            print("Error!  User must donate for this to work.")
            self.config['main']['is_free_account'] = True #CAM
#CAM            return False

        return True


# pylama:ignore=E722,E303
import json
import urllib.error
import urllib.parse
import urllib.request
import logging
from datetime import datetime

import lib.locast_service
from lib.l2p_tools import handle_url_except


class TVHLocastService(lib.locast_service.LocastService):
    config = None

    def __init__(self, location, config):
        super().__init__(location)
        self.config = config
        self.logger = logging.getLogger(__name__)

    @handle_url_except
    def validate_user(self):
        self.logger.debug('Validating User Info...')

        # get user info and make sure we donated
        user_req = urllib.request.Request(
            'https://api.locastnet.org/api/user/me',
            headers={'Content-Type': 'application/json',
                'authorization': 'Bearer ' + self.current_token,
                'User-agent': self.DEFAULT_USER_AGENT})

        user_opn = urllib.request.urlopen(user_req)
        user_res = json.load(user_opn)
        user_opn.close()

        self.logger.debug('User didDonate: {}'.format(user_res['didDonate']))
        # Check if the user has donated, and we got an actual expiration date.
        if user_res['didDonate'] and user_res['donationExpire']:
            donate_exp = datetime.fromtimestamp(user_res['donationExpire'] / 1000)
            self.logger.debug('User donationExpire: {}'.format(donate_exp))
            if not datetime.now() <= donate_exp:
                self.logger.info("User's donation ad-free period has expired.")
                self.config['freeaccount']['is_free_account'] = True
            else:
                self.logger.info('User has an active subscription.')
                self.config['freeaccount']['is_free_account'] = False
        else:
            self.logger.info('User is a free account.')
            self.config['freeaccount']['is_free_account'] = True
        return True

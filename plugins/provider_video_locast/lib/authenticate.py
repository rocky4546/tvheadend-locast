import logging
import urllib
import requests

from lib.tvheadend.decorators import handle_url_except
from lib.tvheadend.decorators import handle_json_except
import lib.tvheadend.exceptions as exceptions

from lib.l2p_tools import clean_exit

from . import constants
from .location import Location


class Authenticate:

    logger = None

    def __init__(self, _config):
        self.config = _config
        self.location = None
        self.token = None
        if not self.login():
            raise exceptions.CabernetException("Locast Login Failed")

    @handle_url_except 
    def login(self):
        if not self.username:
            self.logger.error("Username not specified in config.ini.  Exiting...")
            return None
        if not self.password:
            self.logger.error("Password not specified in config.ini.  Exiting...")
            return None
        if self.config['main']['login_invalid'] is not None:
            self.logger.error('Unable to login due to invalid logins.  Clear config entry login_invalid to try again')
            return None

        self.logger.info("Logging into Locast...")
        self.token = self.get_token()
        if not self.token:
            self.logger.error('Invalid Locast Login Credentials. Exiting...')
            current_time = str(int(time.time()))
            config_obj.write('main', 'login_invalid', current_time)
            return None
        return self.validate_user()

    @handle_json_except 
    @handle_url_except 
    def get_token(self):
        login_url = "https://api.locastnet.org/api/user/login"
        login_headers = {'Content-Type': 'application/json', 'User-agent': constants.DEFAULT_USER_AGENT}
        login_json = ('{"username":"' + self.username + '","password":"' + self.password + '"}').encode("utf-8")
        login_rsp = requests.post(login_url, data=login_json, headers=login_headers)
        login_rsp.raise_for_status()
        login_result = login_rsp.json()
        return login_result["token"]

    @handle_json_except 
    @handle_url_except
    def validate_user(self):
        self.logger.debug('Validating User Info...')
        user_rsp = requests.get(
            'https://api.locastnet.org/api/user/me',
            headers={'Content-Type': 'application/json',
                'authorization': 'Bearer ' + self.token,
                'User-agent': constants.DEFAULT_USER_AGENT})
        user_rsp.raise_for_status()
        user_result = user_rsp.json()

        if user_result['didDonate'] and user_result['donationExpire']:
            donate_exp = datetime.fromtimestamp(user_result['donationExpire'] / 1000)
            self.logger.debug('User donationExpire: {}'.format(donate_exp))
            if not datetime.now() <= donate_exp:
                self.logger.info("User's donation has expired. Setting User to free account")
                self.is_free_account = True
            else:
                self.logger.info('User has an active subscription.')
                self.is_free_account = False
        else:
            self.logger.info('User is a free account.')
            self.is_free_account = True
        return True

    @property
    def is_free_account(self):
        self.config['freeaccount']['is_free_account']

    @is_free_account.setter
    def is_free_account(self, state):
        self.config['freeaccount']['is_free_account'] = state

    @property
    def username(self):
        return self.config['main']['locast_username']

    @property
    def password(self):
        return self.config['main']['locast_password']        


Authenticate.logger = logging.getLogger(__name__)

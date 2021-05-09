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

import json
import logging
import urllib.request
import time
from datetime import datetime

from lib.common.decorators import handle_url_except
from lib.common.decorators import handle_json_except
import lib.common.exceptions as exceptions

from . import constants


class Authenticate:

    logger = None

    def __init__(self, _config_obj, _section):
        self.config_obj = _config_obj
        self.section = _section
        self.token = None
        self.login()

    @handle_url_except 
    def login(self):
        if not self.username:
            return None
        if not self.password:
            return None
        if self.config_obj.data[self.section]['login-invalid'] is not None:
            self.logger.error('{} Unable to login due to invalid logins.  Clear config entry login_invalid to try again'.format(self.section))
            raise exceptions.CabernetException('Locast Login Failed')

        self.logger.info('Logging into Locast [{}]'.format(self.section))
        self.token = self.get_token()
        if not self.token:
            self.logger.error('Invalid Locast Login Credentials. Disabling instance')
            current_time = str(int(time.time()))
            self.config_obj.write(self.section, 'login-invalid', current_time)
            raise exceptions.CabernetException("Locast Login Failed")
        return self.validate_user()

    @handle_json_except 
    @handle_url_except 
    def get_token(self):
        login_url = "https://api.locastnet.org/api/user/login"
        login_headers = {'Content-Type': 'application/json', 'User-agent': constants.DEFAULT_USER_AGENT}
        login_json = ('{"username":"' + self.username + '","password":"' + self.password + '"}').encode("utf-8")
        login_req = urllib.request.Request(login_url, data=login_json, headers=login_headers)
        with urllib.request.urlopen(login_req) as resp:
            login_result = json.load(resp)
        return login_result["token"]

    @handle_json_except 
    @handle_url_except
    def validate_user(self):
        self.logger.debug('Validating User Info...')
        url = 'https://api.locastnet.org/api/user/me'
        header = {'Content-Type': 'application/json',
                'authorization': 'Bearer ' + self.token,
                'User-agent': constants.DEFAULT_USER_AGENT}
        req = urllib.request.Request(url, headers=header)
        with urllib.request.urlopen(req) as resp:
            user_result = json.load(resp)

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
        return self.config_obj.data[self.section]['is_free_account']

    @is_free_account.setter
    def is_free_account(self, state):
        self.config_obj.data[self.section]['is_free_account'] = state

    @property
    def username(self):
        return self.config_obj.data[self.section]['login-username']

    @property
    def password(self):
        return self.config_obj.data[self.section]['login-password']        


Authenticate.logger = logging.getLogger(__name__)

'''
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
'''

import logging
import urllib
import requests
import time


from lib.tvheadend.utils import clean_exit

from .channels import Channels
from .epg import EPG
from .location import Location
from .authenticate import Authenticate



class Locast:

    logger = None

    def __init__(self, _config, _namespace):
        self.config = _config
        self.namespace = _namespace
        self.auth = Authenticate(self.config)
        self.location = Location(self.config)
        self.channels = Channels(self)
        self.epg = EPG(self)
        time.sleep(1)
        
    def refresh_channels(self):
        self.channels.refresh_channels()

    def refresh_epg(self, _instance=None):
        self.epg.refresh_epg(_instance)

    def get_channel_uri(self, sid, _instance=None):
        return self.channels.get_channel_uri(sid, _instance)

    @property
    def name(self):
        return self.namespace
    
Locast.logger = logging.getLogger(__name__)

import logging
import urllib
import requests
import time


from lib.l2p_tools import clean_exit

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


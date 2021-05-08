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

import logging

import lib.common.utils as utils
from .location import Location
from .channels import Channels
from .epg import EPG



class LocastInstance:

    logger = None

    def __init__(self, _locast, _instance):
        self.config_obj = _locast.config_obj
        self.instance = _instance
        self.locast = _locast
        self.location = Location(self)
        self.channels = Channels(self)
        self.epg = EPG(self)

    def refresh_channels(self):
        if self.config_obj.data[self.config_section]['enabled']:
            self.channels.refresh_channels()

    def refresh_epg(self):
        if self.config_obj.data[self.config_section]['enabled']:
            self.epg.refresh_epg2()

    def get_channel_uri(self, sid):
        if self.config_obj.data[self.config_section]['enabled']:
            return self.channels.get_channel_uri(sid)
        else:
            return None

    @property
    def config_section(self):
        return utils.instance_config_section(self.locast.name, self.instance)


LocastInstance.logger = logging.getLogger(__name__)

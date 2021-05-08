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


from .channels import Channels
from .epg import EPG
from .authenticate import Authenticate
from .stream import Stream
from .locast_instance import LocastInstance

class Locast:

    logger = None

    def __init__(self, _plugin):
        self.config_obj = _plugin.config_obj
        self.config = _plugin.config_obj.data
        self.namespace = _plugin.namespace
        self.auth = Authenticate(_plugin.config_obj)
        self.locast_instances = {}
        for inst in _plugin.instances:
            self.locast_instances[inst] = LocastInstance(self, inst)
        self.stream = Stream(self)
        
    def refresh_channels(self, _instance=None):
        if _instance is None:
            for key, instance in self.locast_instances.items():
                instance.channels.refresh_channels()
        else:
            self.locast_instances[_instance].channels.refresh_channels()

    def refresh_epg(self, _instance=None):
        if _instance is None:
            for key, instance in self.locast_instances.items():
                instance.epg.refresh_epg()
        else:
            self.locast_instances[_instance].epg.refresh_epg()

    def get_channel_uri(self, sid, _instance=None):
        return self.locast_instances[_instance].channels.get_channel_uri(sid)

    def is_time_to_refresh(self, _last_refresh):
        return self.stream.is_time_to_refresh(_last_refresh)

    @property
    def name(self):
        return self.namespace


Locast.logger = logging.getLogger(__name__)

"""
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

from lib.db.db_scheduler import DBScheduler
from lib.plugins.plugin_obj import PluginObj

from .authenticate import Authenticate
from .locast_instance import LocastInstance


class Locast(PluginObj):

    def __init__(self, _plugin):
        super().__init__(_plugin)
        self.auth = Authenticate(_plugin.config_obj, self.namespace.lower())
        for inst in _plugin.instances:
            self.instances[inst] = LocastInstance(self, inst)
        self.scheduler_tasks()

    def refresh_channels(self, _instance=None):
        if _instance is None:
            for key, instance in self.instances.items():
                instance.refresh_channels()
        else:
            self.instances[_instance].refresh_channels()

    def refresh_epg(self, _instance=None):
        if _instance is None:
            for key, instance in self.instances.items():
                instance.refresh_epg()
        else:
            self.instances[_instance].refresh_epg()

    def get_channel_uri(self, sid, _instance=None):
        return self.instances[_instance].get_channel_uri(sid)

    def is_time_to_refresh(self, _last_refresh, _instance):
        return self.instances[_instance].is_time_to_refresh(_last_refresh)

    def scheduler_tasks(self):
        scheduler_db = DBScheduler(self.config_obj.data)
        if scheduler_db.save_task(
                'Channels',
                'Refresh Locast Channels',
                self.name,
                None,
                'refresh_channels',
                20,
                'inline',
                'Pulls channel lineup from Locast'
                ):
            scheduler_db.save_trigger(
                'Channels',
                'Refresh Locast Channels',
                'startup')
            scheduler_db.save_trigger(
                'Channels',
                'Refresh Locast Channels',
                'daily',
                timeofday='22:00'
                )
        if scheduler_db.save_task(
                'EPG',
                'Refresh Locast EPG',
                self.name,
                None,
                'refresh_epg',
                10,
                'thread',
                'Pulls channel program data from Locast'
                ):
            scheduler_db.save_trigger(
                'EPG',
                'Refresh Locast EPG',
                'startup')
            scheduler_db.save_trigger(
                'EPG',
                'Refresh Locast EPG',
                'interval',
                interval=700
                )

    @property
    def name(self):
        return self.namespace


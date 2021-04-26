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


class Stream:

    def __init__(self, _plugins, _hdhr_queue):
        self.logger = logging.getLogger(__name__)
        self.plugins = _plugins
        self.hdhr_queue = _hdhr_queue

    def put_hdhr_queue(self, _index, _channel, _status):
        if not self.plugins.config_obj.data['hdhomerun']['disable_hdhr']:
            self.hdhr_queue.put(
                {'tuner': _index, 'channel': _channel, 'status': _status})

    def find_tuner(self, _ch_num, _tuner):
        # keep track of how many tuners we can use at a time
        index = -1
        for index, scan_status in enumerate(_tuner.rmg_station_scans):
            # the first idle tuner gets it
            if scan_status == 'Idle':
                _tuner.rmg_station_scans[index] = _ch_num
                self.put_hdhr_queue(index, _ch_num, 'Stream')
                break
        return index

    def set_service_name(self, _channel_dict):
        prefix = self.plugins.config_obj.data[_channel_dict['namespace'].lower()]['epg-prefix']
        suffix = self.plugins.config_obj.data[_channel_dict['namespace'].lower()]['epg-suffix']
        if prefix is None:
            prefix = ""
        if suffix is None:
            suffix = ""
        service_name = prefix + \
            str(_channel_dict['number']) + \
            suffix + \
            ' ' + _channel_dict['display_name']
        return service_name

    def get_stream_uri(self, _channel_dict):
        return self.plugins.plugins[_channel_dict['namespace']] \
            .plugin_obj.get_channel_uri(_channel_dict['uid'], _channel_dict['instance'])

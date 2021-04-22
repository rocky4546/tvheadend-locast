'''
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
'''

import time
import urllib
import ssl
import zipfile
import os
import datetime
import json
import logging
import requests
import datetime
import sys

import lib.m3u8 as m3u8
from lib.tvheadend.utils import clean_exit
from lib.tvheadend.filelock import FileLock
import lib.tvheadend.exceptions as exceptions
from lib.tvheadend.decorators import handle_url_except
from lib.tvheadend.decorators import handle_json_except
from lib.db.db_channels import DBChannels

from . import constants
from .fcc_data import FCCData


class Channels:

    logger = None

    def __init__(self, _locast):
        self.locast = _locast
        self.db = DBChannels(self.locast.config)

    def refresh_channels(self):
        self.logger.debug('Checking Channel data for {}'.format(self.locast.name))
        #fcc_stations = FCCData(self.locast)
        last_update = self.db.get_status(self.locast.name, constants.INSTANCE)
        update_needed = False
        if not last_update:
            update_needed = True
        else:
            delta = datetime.datetime.now() - last_update
            if delta.days >= self.locast.config['locast']['channel_update_timeout']:
                update_needed = True
        if update_needed:
            ch_dict = self.get_locast_channels()
            self.db.save_channel_list(self.locast.name, constants.INSTANCE, ch_dict)


    @handle_json_except
    @handle_url_except 
    def get_locast_channels(self):
        channels_url = 'https://api.locastnet.org/api/watch/epg/{}' \
            .format(self.locast.location.dma)
        url_headers = {
            'Content-Type': 'application/json', 
            'authorization': 'Bearer {}'.format(self.locast.auth.token),
            'User-agent': constants.DEFAULT_USER_AGENT}
        ch_rsp = requests.get(channels_url, headers=url_headers)
        ch_rsp.raise_for_status()
        ch_json = ch_rsp.json()
        ch_rsp.close()

        ch_list = []
        if len(ch_json) == 0:
            self.logger.warning('Locast HTTP Channel Request Failed')
            raise exceptions.CabernetException('Locast HTTP Channel Request Failed')
            
        self.logger.info("{}: Found {} stations for DMA {}".format(self.locast.name, len(ch_json), 
            str(self.locast.location.dma)))

        for locast_channel in ch_json:
            ch_id = str(locast_channel['id'])
            ch_callsign = locast_channel['name']
            if 'logoUrl' in locast_channel.keys():
                thumbnail = locast_channel['logoUrl']
            elif 'logo226Url' in locast_channel.keys():
                thumbnail = locast_channel['logo226Url']
            if 'videoProperties' in locast_channel['listings'][0]:
                if 'HD' in locast_channel['listings'][0]['videoProperties']:
                    hd = 1
                else:
                    hd = 0

            try:
                assert (float(locast_channel['callSign'].split()[0]))
                channel = locast_channel['callSign'].split()[0]
                friendly_name = locast_channel['callSign'].split()[1]
                channel = {
                    'id': ch_id,
                    'callsign': ch_callsign,
                    'number': channel,
                    'name': friendly_name,
                    'HD': hd,
                    'group_hdtv': self.locast.config['locast']['m3u_group_hdtv'],
                    'group_sdtv': self.locast.config['locast']['m3u_group_sdtv'],
                    'groups_other': None,    # array list of groups/categories
                    'thumbnail': thumbnail
                    }
                ch_list.append(channel)
            except ValueError:
                self.logger.warning('################### CALLSIGN ERROR Channel ignored: {} {}'.format(ch_id, locast_channel['callSign']))
        return ch_list



    @handle_json_except
    @handle_url_except 
    def get_channel_uri(self, _channel_id, _instance):
        self.logger.info(self.locast.name+ ": Getting station info for " + _channel_id)
        stream_url = ''.join([
            'https://api.locastnet.org/api/watch/station/',
            str(_channel_id), '/', 
            self.locast.location.latitude, '/', 
            self.locast.location.longitude])
        stream_headers = {'Content-Type': 'application/json',
            'authorization': 'Bearer ' + self.locast.auth.token,
            'User-agent': constants.DEFAULT_USER_AGENT}
        stream_rsp = requests.get(stream_url, headers=stream_headers)
        stream_rsp.raise_for_status()
        stream_result = stream_rsp.json()
        self.logger.debug("Determining best video stream for " + _channel_id + "...")
        bestStream = None

        # find the heighest stream url resolution and save it to the list
        videoUrlM3u = m3u8.load(stream_result['streamUrl'], 
            headers={'authorization': 'Bearer ' + self.locast.auth.token,
            'User-agent': constants.DEFAULT_USER_AGENT})
        self.logger.debug("Found " + str(len(videoUrlM3u.playlists)) + " Playlists")

        if len(videoUrlM3u.playlists) > 0:
            for videoStream in videoUrlM3u.playlists:
                if bestStream is None:
                    bestStream = videoStream

                elif ((videoStream.stream_info.resolution[0] > bestStream.stream_info.resolution[0]) and
                      (videoStream.stream_info.resolution[1] > bestStream.stream_info.resolution[1])):
                    bestStream = videoStream

                elif ((videoStream.stream_info.resolution[0] == bestStream.stream_info.resolution[0]) and
                      (videoStream.stream_info.resolution[1] == bestStream.stream_info.resolution[1]) and
                      (videoStream.stream_info.bandwidth > bestStream.stream_info.bandwidth)):
                    bestStream = videoStream


            if bestStream is not None:
                self.logger.debug(_channel_id + " will use " +
                      str(bestStream.stream_info.resolution[0]) + "x" + str(bestStream.stream_info.resolution[1]) +
                      " resolution at " + str(bestStream.stream_info.bandwidth) + "bps")

                return bestStream.absolute_uri

        else:
            self.logger.debug("No variant streams found for this station.  Assuming single stream only.")
            return stream_result['streamUrl']


Channels.logger = logging.getLogger(__name__)

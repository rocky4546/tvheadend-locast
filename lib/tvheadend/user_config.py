import os
import random
import configparser
import pathlib

import lib.user_config
import lib.tvheadend.utils as utils

def get_config(script_dir, opersystem, args):
    return TVHUserConfig(script_dir, opersystem, args)


class TVHUserConfig( lib.user_config.UserConfig ):

    def __init__(self, script_dir, opersystem, args):
        self.data['main'].update({
                    'quiet': True,  # disables all generic print from locast2plex and logging
                    'quiet_print': True,  # tries to disable all the print statements in locast2plex only
                })
        self.data.update({
            'freeaccount': {
                'is_free_account': True,  # automatically internally set
                # *pkt_rcvd values will cause the 'bytes_per_read' to be adjusted
                'min_pkt_rcvd': 10,     # minimum video packets received per locast stream read
                'max_pkt_rcvd': 100,    # maximum video packets received per locast stream read
                'pts_minimum': 10000000, # value = 90000 * seconds.  locast has shown
                    # the pts value is normally less than 1 million
                    # system drops packets that have a low pts
                'pts_max_delta': 10000000, # delta for a single buffer read from beginning to end
                    # system drops packets outside of the delta pts
                    # normally will be over 200,000,000 when locast sends a bad packet
                    # large pts deltas will cause tvheadend to stop recording
                    # default deltas are normally less than 500,000 but 
                    # are based on 'max_pkt_rcvd' value
                'refresh_rate': 800, # in seconds.  Between 10 and 15 minutes. -1 means ignore  
                    # reduces the impacts to locast ads.  Ads can induce a 6 second window where
                    # no video is provided
        }})
        self.data.update({
            'epg': {
                'epg_prefix': '',             # prefix added to the channel number for epg and service names
                'epg_suffix': '',             # suffix added to the channel number for epg and service names
                'description': 'extend',      # 'default', 'brief', 'extend'
                'genre': 'tvheadend',         # 'default', 'tvheadend'
        }})
        self.data.update({
            'player': {
                'epg_suffix': '', # suffix added to the channel number for epg and service names
        }})
        super().__init__(script_dir, opersystem, args)
    
    
    def import_config(self):
        self.config_handler.read(self.config_file)
        for each_section in self.config_handler.sections():
            for (each_key, each_val) in self.config_handler.items(each_section):
                try:
                    self.data[each_section.lower()][each_key.lower()] = each_val
                except KeyError:
                    self.data.update({
                        each_section.lower(): {
                    }})
                    self.data[each_section.lower()][each_key.lower()] = each_val

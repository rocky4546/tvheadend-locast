import os
import sys
import platform 
import random
import configparser
import pathlib
import logging
import base64
import cryptography
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet


import lib.user_config
import lib.tvheadend.utils as utils

ENCRYPT_STRING = 'ENC::'

def get_config(script_dir, opersystem, args):
    return TVHUserConfig(script_dir, opersystem, args)


class TVHUserConfig( lib.user_config.UserConfig ):

    def __init__(self, script_dir, opersystem, args):
        self.data['main'].update({
            'quiet': True,  # disables all generic print from locast2plex and logging
            'quiet_print': True,  # tries to disable all the print statements in locast2plex only
            'ffprobe_path': None, 
            'encrypt_key': None,
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
                'ffprobe_path': None, 
        }})
        super().__init__(script_dir, opersystem, args)
        self.tvh_config_adjustments(opersystem, script_dir)
    
    
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


    def tvh_config_adjustments(self, opersystem, script_dir):
    
        if not self.data['main']['ffmpeg_path']:
            if opersystem in ['Windows']:
                base_ffmpeg_dir = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                self.data['main']['ffmpeg_path'] = pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe')
            else:
                self.data['main']['ffmpeg_path'] = 'ffmpeg'
        else:
            if not os.path.exists(self.data['main']['ffmpeg_path']):
                if opersystem in ['Windows']:
                    base_ffmpeg_dir = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                    self.data['main']['ffmpeg_path'] = pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe')
                else:
                    self.data['main']['ffmpeg_path'] = 'ffmpeg'
        if not self.data['player']['ffprobe_path']:
            if opersystem in ['Windows']:
                base_ffprobe_dir = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                self.data['player']['ffprobe_path'] = pathlib.Path(base_ffprobe_dir).joinpath('ffprobe.exe')
            else:
                self.data['player']['ffprobe_path'] = 'ffprobe'

        if self.data['main']['encrypt_key'] is None:
            self.set_fernet_key()
            if self.data['main']['locast_password'].startswith(ENCRYPT_STRING):
                # encrypted
                self.data['main']['locast_password'] \
                    = self.decrypt(self.data['main']['locast_password'])
                if self.data['main']['locast_password'] == 'UNKNOWN':
                    logging.error('Unable to decrypt password. ' \
                        + 'Try updating password in config file to clear text')
            else:
                # not encrypted
                clear_pwd = self.data['main']['locast_password']
                encrypted_pwd = self.encrypt(self.data['main']['locast_password'])
                self.write('main', 'locast_password', encrypted_pwd)
                self.data['main']['locast_password'] = clear_pwd

    ####### ENCRYPTION SECTION #######

    def set_fernet_key(self):
        opersystem = platform.system()
        # is there a key already generated
        if opersystem in ['Windows']:
            key_file = os.getenv('LOCALAPPDATA')+'/.locast/key.txt'
        else:  #linux
            key_file = os.getenv('HOME')+'/.locast/key.txt'
        try:
            with open(key_file, 'rb') as f:
                key = f.read()
                self.data['main']['encrypt_key'] = key
        except FileNotFoundError:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
                self.data['main']['encrypt_key'] = key


    def encrypt(self, clearstr):
        if clearstr.startswith(ENCRYPT_STRING):
            # already encrypted_pwd
            return clearstr
        else:
            f = Fernet(self.data['main']['encrypt_key'])
            token = f.encrypt(clearstr.encode())
            return ENCRYPT_STRING + token.decode()


    def decrypt(self, encstr):
        if encstr.startswith(ENCRYPT_STRING):
            f = Fernet(self.data['main']['encrypt_key'])
            try:
                token = f.decrypt(encstr[len(ENCRYPT_STRING):].encode())
            except cryptography.fernet.InvalidToken:
                # occurs when mutiple users are running the app.
                # need to signal the caller that we have issues
                logging.warn("Unable to decrypt string.")
                return 'UNKNOWN'

            return token.decode()
        else:
            return encstr

    ####### END ENCRYPTION SECTION #######



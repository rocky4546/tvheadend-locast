import os
import sys
import platform 
import random
import configparser
import pathlib
import logging
import base64
import socket
import copy
import string
import struct

try:
    import cryptography
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet
    CRYPTO_LOADED = True
except ImportError:
    print('Unable to load cryptography module, will not encrypt passwords')
    CRYPTO_LOADED = False


import lib.user_config
import lib.tvheadend.utils as utils

ENCRYPT_STRING = 'ENC::'

def get_config(script_dir, opersystem, args):
    return TVHUserConfig(script_dir, opersystem, args)


class TVHUserConfig( lib.user_config.UserConfig ):

    def __init__(self, script_dir, opersystem, args):
        self.data['main'].update({
            'quiet_print': True,  # tries to disable all the print statements in locast2plex only
            'encrypt_key': None,  # internally used
            'use_encryption': True, # determines if the password is encrypted
            'login_invalid': None,  # set to the time when the login failed.  Remove setting to allow login
            'login_timeout': 4000,  # NOT IMPLEMENTED number of seconds to wait once an invalid login occurs
            'local_ip': '0.0.0.0',    # 0.0.0.0 it will use the active ip address on the system
            'disable_web_config': False, # disables the config.json and configform.html web pages
            #bytes_per_read is a number multiplied by 1316
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
                'description': 'extend',      # 'normal', 'brief', 'extend'
                'genre': 'tvheadend',         # 'normal', 'tvheadend'
        }})
        self.data.update({
            'player': {
                'ffprobe_path': None, 
        }})
        self.data.update({
            'hdhomerun': {
                'disable_hdhr': True,   # used to support HDHomerun auto-discovery.
                'hdhr_id': '104ed44c',  # This is a 4 byte with CRC_4 hex string.  EX: 104ed44c
                                        # so the id must meet CRC hash requirements
                'udp_netmask': None,    # This keeps the amount of broadcast messages down.
                                        # example: '192.168.1.120/32' makes it respond only to that address
        }})
                


        self.config_defaults = copy.deepcopy(self.data)
        super().__init__(script_dir, opersystem, args)
        self.tvh_config_adjustments(opersystem, script_dir)
    
        # list of functions to call when the variable is updated
        self.data_functions = {
            'main': {
                'epg_update_frequency': utils.noop,
                'bytes_per_read': utils.noop,
                'verbose': utils.noop,
                'quiet_print': utils.noop,
            },
            'freeaccount': {
                'refresh_rate': utils.noop,
                'min_pkt_rcvd': utils.noop,
                'max_pkt_rcvd': utils.noop,
                'pts_minimum': utils.noop,
                'pts_max_delta': utils.noop,
            },
            'logger_root': {
                'level': utils.logging_refresh,
            },
            'handler_loghandler': {
                'formatter': utils.logging_refresh,
            }
        }

    
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


    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP


    def hdhr_validate_device_id(self, device_id):
        hex_digits = set(string.hexdigits)
        if len(device_id) != 8:
            logging.error('ERROR: HDHR Device ID must be 8 hexidecimal values')
            return False
        if not all(c in hex_digits for c in device_id):
            logging.error('ERROR: HDHR Device ID characters must all be hex (0-A)')
            return False
        device_id_bin = bytes.fromhex(device_id)
        cksum_lookup = [0xA, 0x5, 0xF, 0x6, 0x7, 0xC, 0x1, 0xB, 0x9, 0x2, 0x8, 0xD, 0x4, 0x3, 0xE, 0x0]
        device_id_int = int.from_bytes(device_id_bin, byteorder='big')
        cksum=0
        cksum ^= cksum_lookup[(device_id_int >> 28) & 0x0F]
        cksum ^= (device_id_int >> 24) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 20) & 0x0F]
        cksum ^= (device_id_int >> 16) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 12) & 0x0F]
        cksum ^= (device_id_int >> 8) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 4) & 0x0F]
        cksum ^= (device_id_int >> 0) & 0x0F
        return (cksum == 0)


    # given a device id, will adjust the last 4 bits to make it valid and return the integer value
    def hdhr_get_valid_device_id(self, device_id):
        hex_digits = set(string.hexdigits)
        if len(device_id) != 8:
            logging.error('ERROR: HDHR Device ID must be 8 hexidecimal values')
            return 0
        if not all(c in hex_digits for c in device_id):
            logging.error('ERROR: HDHR Device ID characters must all be hex (0-A)')
            return 0
        device_id_bin = bytes.fromhex(device_id)
        cksum_lookup = [0xA, 0x5, 0xF, 0x6, 0x7, 0xC, 0x1, 0xB, 0x9, 0x2, 0x8, 0xD, 0x4, 0x3, 0xE, 0x0]
        device_id_int = int.from_bytes(device_id_bin, byteorder='big')
        cksum=0
        cksum ^= cksum_lookup[(device_id_int >> 28) & 0x0F]
        cksum ^= (device_id_int >> 24) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 20) & 0x0F]
        cksum ^= (device_id_int >> 16) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 12) & 0x0F]
        cksum ^= (device_id_int >> 8) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 4) & 0x0F]
        new_dev_id = (device_id_int & 0xFFFFFFF0) + cksum
        return struct.pack('>I',new_dev_id).hex()

    # removes sensitive data from config and returns a copy
    def filter_config_data(self):
        filtered_config = copy.deepcopy(self.data)
        del filtered_config['main']['locast_password']
        del filtered_config['main']['locast_username']
        del filtered_config['main']['disable_ssdp']
        del filtered_config['main']['override_latitude']
        del filtered_config['main']['override_longitude']
        del filtered_config['main']['override_zipcode']
        del filtered_config['main']['mock_location']
        del filtered_config['main']['use_old_plex_interface']
        del filtered_config['main']['encrypt_key']
        del filtered_config['main']['uuid']
        return filtered_config


    def detect_change(self, section, key, updated_data):
        try:
            current_value = self.data[section][key]
            if type(current_value) is int:
                updated_data[section][key][0] = int(updated_data[section][key][0])
            elif type(current_value) is bool:
                if key in updated_data[section].keys():
                    updated_data[section][key][0] = utils.str2bool(updated_data[section][key][0])
                else:
                    updated_data[section][key] = [False]
            elif type(current_value) is str:
                pass
            elif current_value is None:
                pass
            else:
                logging.debug('unknown value type for [{}][{}]  type is {}'.format(section, key, type(self.data[section][key])))

            if self.data[section][key] != updated_data[section][key][0]:
                updated_data[section][key].append(True)
            else:
                updated_data[section][key].append(False)
            
        except KeyError:
            # not found, use default value if available
            try:
                if self.data[section][key] != self.config_defaults[section][key]:
                    updated_data[section][key] = [None, True]
            except KeyError:
                logging.debug('KeyError-2 [{}][{}]'.format(section, key))
                # no default, so assume using the string as is
                if self.data[section][key] != updated_data[section][key]:
                    updated_data[section][key].append(True)
        
        
    def update_config(self, updated_data):
        # need to go through manually to see which are missing
        #based on configform.html, the keys are
        # TEXT AND SELECT BASED VALUES
        updated_data['main']['plex_accessible_ip'].append(False)
        updated_data['freeaccount']['is_free_account'].append(False)
        
        #make sure all sections are listed in updated_data
        if 'main' not in updated_data.keys():
            updated_data['main'] = {}
        if 'freeaccount' not in updated_data.keys():
            updated_data['freeaccount'] = {}
        if 'epg' not in updated_data.keys():
            updated_data['epg'] = {}
        if 'logger_root' not in updated_data.keys():
            updated_data['logger_root'] = {}
        if 'handler_loghandler' not in updated_data.keys():
            updated_data['handler_loghandler'] = {}
        
        self.detect_change('main', 'local_ip', updated_data)
        self.detect_change('main', 'plex_accessible_port', updated_data)
        self.detect_change('main', 'tuner_count', updated_data)
        self.detect_change('main', 'concurrent_listeners', updated_data)
        self.detect_change('main', 'epg_update_frequency', updated_data)
        self.detect_change('main', 'epg_update_days', updated_data)
        self.detect_change('main', 'bytes_per_read', updated_data)
        self.detect_change('main', 'login_invalid', updated_data)
        self.detect_change('freeaccount', 'refresh_rate', updated_data)
        self.detect_change('freeaccount', 'min_pkt_rcvd', updated_data)
        self.detect_change('freeaccount', 'max_pkt_rcvd', updated_data)
        self.detect_change('freeaccount', 'pts_minimum', updated_data)
        self.detect_change('freeaccount', 'pts_max_delta', updated_data)
        self.detect_change('epg', 'epg_prefix', updated_data)
        self.detect_change('epg', 'epg_suffix', updated_data)
        
        # CHECKBOX BASED VALUES
        self.detect_change('main', 'verbose', updated_data)
        self.detect_change('main', 'quiet_print', updated_data)
        self.detect_change('main', 'use_encryption', updated_data)

        # SELECT BASED VALUES
        self.detect_change('epg', 'description', updated_data)
        self.detect_change('epg', 'genre', updated_data)
        self.detect_change('logger_root', 'level', updated_data)
        self.detect_change('handler_loghandler', 'formatter', updated_data)

        # save the changes to config.ini and self.data
        results = '<hr><h3>Status Results</h3><ul>'
        for key in updated_data.keys():
            results += self.save_config_section(key, updated_data)
        with open(self.config_file, 'w') as config_file:
            self.config_handler.write(config_file)

        # need to inform things that changes occurred...
        restart = False
        for section in updated_data.keys():
            for (key, value) in updated_data[section].items():
                if value[1]:
                    try:
                        self.data_functions[section][key](self)
                        results += '<li>[{}][{}] implemented</li>'.format(section, key)
                    except KeyError:
                        restart = True
                        #logging.debug('function missing for key {}'.format(key))
        if restart:
            results += '</ul><b>Service may need to be restarted if not all changes were implemented</b><hr><br>'
        else:
            results += '</ul><hr><br>'
        
        return results

    def save_config_section(self, section, updated_data):
        results = ''
        for (key, value) in updated_data[section].items():
            if value[1]:
                if value[0] is None:
                    # use default and remove item from config.ini
                    self.config_handler.remove_option(section, key)
                    self.data[section][key] = self.config_defaults[section][key]
                    logging.debug('Config Update: Removed [{}][{}]'.format(section, key))
                    results += '<li>Removed [{}][{}] from config.ini, using default value</li>' \
                        .format(section, key)
                else:
                    # set new value
                    self.config_handler.set(section, key, str(updated_data[section][key][0]))
                    self.data[section][key] = updated_data[section][key][0]
                    logging.debug('Config Update: Changed [{}][{}] to {}'.format(section, key, updated_data[section][key][0]))
                    results += '<li>Updated [{}][{}] to {}</li>' \
                        .format(section, key, updated_data[section][key][0])
        return results


    # We make the last adjustments here after super() updates
    def tvh_config_adjustments(self, opersystem, script_dir):
    
        self.data['main']['reporting_model'] = "tvhl"
        self.data['main']['reporting_friendly_name'] = "TVHeadend-Locast"
        self.data['main']['reporting_firmware_name'] = "TVHeadend-Locast"
        self.data['main']['reporting_firmware_ver'] = 'v' + utils.get_version_str()
    
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

        if self.data['main']['local_ip'] == '0.0.0.0':
            self.data["main"]['bind_ip'] = '0.0.0.0'
            self.data['main']['plex_accessible_ip'] = self.get_ip()
        else:
            self.data['main']['bind_ip'] = self.data['main']['local_ip']
            self.data['main']['plex_accessible_ip'] = self.data['main']['local_ip']

        hdhr_device = self.data['hdhomerun']['hdhr_id']
        valid_hdhr_device = self.hdhr_get_valid_device_id(hdhr_device)
        if hdhr_device != valid_hdhr_device:
            logging.error('CONFIG: [hdhomerun][hdhr_id] is invalid, using valid id {}' \
                .format(valid_hdhr_device))
            self.data['hdhomerun']['hdhr_id'] = valid_hdhr_device

        # INTEGER PARAMETERS
        if type(self.data['main']['tuner_count']) is not int:
            self.data['main']['tuner_count'] = int(self.data['main']['tuner_count'])
        if type(self.data['main']['epg_update_frequency']) is not int:
            self.data['main']['epg_update_frequency'] = int(self.data['main']['epg_update_frequency'])
        if type(self.data['main']['epg_update_days']) is not int:
            self.data['main']['epg_update_days'] = int(self.data['main']['epg_update_days'])
        if type(self.data['main']['fcc_delay']) is not int:
            self.data['main']['fcc_delay'] = int(self.data['main']['fcc_delay'])
        if type(self.data['main']['login_timeout']) is not int:
            self.data['main']['login_timeout'] = int(self.data['main']['login_timeout'])
        if type(self.data['freeaccount']['min_pkt_rcvd']) is not int:
            self.data['freeaccount']['min_pkt_rcvd'] = int(self.data['freeaccount']['min_pkt_rcvd'])
        if type(self.data['freeaccount']['max_pkt_rcvd']) is not int:
            self.data['freeaccount']['max_pkt_rcvd'] = int(self.data['freeaccount']['max_pkt_rcvd'])
        if type(self.data['freeaccount']['pts_minimum']) is not int:
            self.data['freeaccount']['pts_minimum'] = int(self.data['freeaccount']['pts_minimum'])
        if type(self.data['freeaccount']['pts_max_delta']) is not int:
            self.data['freeaccount']['pts_max_delta'] = int(self.data['freeaccount']['pts_max_delta'])
        if type(self.data['freeaccount']['refresh_rate']) is not int:
            self.data['freeaccount']['refresh_rate'] = int(self.data['freeaccount']['refresh_rate'])


        # BOOLEAN PARAMETERS
        if type(self.data['main']['quiet_print']) is str:
            self.data['main']['quiet_print'] = self.config_handler.getboolean('main', 'quiet_print')
        if type(self.data['main']['use_encryption']) is str:
            self.data['main']['use_encryption'] = self.config_handler.getboolean('main', 'use_encryption')
        if not self.data['main']['disable_ssdp']:
            # ssdp does not currently work, disable it is the default is used
            self.data['main']['disable_ssdp'] = True
        elif type(self.data['main']['disable_ssdp']) is str:
            self.data['main']['disable_ssdp'] = self.config_handler.getboolean('main', 'disable_ssdp')
        if type(self.data['main']['verbose']) is str:
            self.data['main']['verbose'] = self.config_handler.getboolean('main', 'verbose')
        if type(self.data['main']['disable_web_config']) is str:
            self.data['main']['disable_web_config'] = self.config_handler.getboolean('main', 'disable_web_config')
        if type(self.data['hdhomerun']['disable_hdhr']) is str:
            self.data['hdhomerun']['disable_hdhr'] = self.config_handler.getboolean('hdhomerun', 'disable_hdhr')

        # changing any types that cause issues with the JSON converter
        if type(self.data['main']['cache_dir']) is not str:
            self.data['main']['cache_dir'] = str(self.data['main']['cache_dir'])
        if type(self.data['main']['ffmpeg_path']) is not str:
            self.data['main']['ffmpeg_path'] = str(self.data['main']['ffmpeg_path'])
        if type(self.data['player']['ffprobe_path']) is not str:
            self.data['player']['ffprobe_path'] = str(self.data['player']['ffprobe_path'])


        if CRYPTO_LOADED and self.data['main']['encrypt_key'] is None \
                and self.data['main']['use_encryption']:
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



import os
import platform
import random
import pathlib
import logging
import socket
import copy
import string
import struct
import uuid
import json
import importlib
import configparser

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


class TVHUserConfig(lib.user_config.UserConfig):

    def __init__(self, script_dir=None, opersystem=None, args=None, config=None):
        self.logger = None

        self.defn_json = self.load_config_defn('lib/tvheadend/config.json')
        self.config_defaults = self.init_default_config(self.defn_json)
        self.data = copy.deepcopy(self.config_defaults)
        if script_dir is not None:
            super().__init__(script_dir, opersystem, args)
            self.tvh_config_adjustments(opersystem, script_dir)
        else:
            self.set_config(config)

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

    def load_config_defn(self, json_file):
        with open(json_file, 'r') as file_defn:
            defn = json.load(file_defn)
        return defn

    def init_default_config(self, config_defn):
        """
        JSON format: [module]['sections'][section]['settings'][setting][metadata]
        section is the section in the ini file
        setting is the name in the ini file
        """
        defaults = {}
        for module in list(config_defn.keys()):
            for section in list(config_defn[module]['sections'].keys()):
                if section not in list(defaults.keys()):
                    defaults[section] = {}
                for setting in list(config_defn[module]['sections'][section]['settings'].keys()):
                    value = config_defn[module]['sections'][section]['settings'][setting]['default']
                    defaults[section][setting] = value
        return defaults

    def set_config(self, _config):
        self.data = copy.deepcopy(_config)
        self.logger = logging.getLogger(__name__)
        
    def import_config(self):
        self.config_handler.read(self.config_file)
        self.data['main']['config_file'] = str(self.config_file)
        utils.logging_setup(self.config_file)
        self.logger = logging.getLogger(__name__)
        
        for each_section in self.config_handler.sections():
            lower_section = each_section.lower()
            if lower_section not in self.data.keys():
                self.data.update({lower_section: {}})
            for (each_key, each_val) in self.config_handler.items(each_section):
                lower_key = each_key.lower()
                self.data[lower_section][lower_key] = \
                    self.fix_value_type(lower_section, lower_key, each_val)


    def fix_value_type(self, _section, _key, _value):
        val_type = self.get_type(_section, _key, _value)
        if val_type == 'boolean':
            return self.config_handler.getboolean(_section, _key)
        elif val_type == 'list':
            if not self.validate_list_item(_section, _key, _value):
                logging.warning('INVALID VALUE ({}) FOR CONFIG ITEM [{}][{}]'
                    .format(_value, _section, _key))
            return _value
        elif val_type == 'integer':
            return int(_value)
        elif val_type == 'float':
            return float(_value)
        else:
            return _value


    def validate_list_item(self, _section, _key, _value):
        for module in list(self.defn_json.keys()):
            for section in list(self.defn_json[module]['sections'].keys()):
                if section == _section:
                    for setting in list(self.defn_json[module]['sections'][section]['settings'].keys()):
                        if setting == _key:
                            if _value in self.defn_json[module]['sections'][section]['settings'][setting]['values']:
                                return True
                            else:
                                return False
        return None
    

    def get_type(self, _section, _key, _value):
        for module in list(self.defn_json.keys()):
            for section in list(self.defn_json[module]['sections'].keys()):
                if section == _section:
                    for setting in list(self.defn_json[module]['sections'][section]['settings'].keys()):
                        if setting == _key:
                            return self.defn_json[module]['sections'][section]['settings'][setting]['type']
        return None

    def call_function(self, func_str):
        mod_name, func_name = func_str.rsplit('.',1)
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        return func(self)
        


    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def hdhr_validate_device_id(self, device_id):
        hex_digits = set(string.hexdigits)
        if len(device_id) != 8:
            self.logger.error('ERROR: HDHR Device ID must be 8 hexidecimal values')
            return False
        if not all(c in hex_digits for c in device_id):
            self.logger.error('ERROR: HDHR Device ID characters must all be hex (0-A)')
            return False
        device_id_bin = bytes.fromhex(device_id)
        cksum_lookup = [0xA, 0x5, 0xF, 0x6, 0x7, 0xC, 0x1, 0xB, 0x9, 0x2, 0x8, 0xD, 0x4, 0x3, 0xE, 0x0]
        device_id_int = int.from_bytes(device_id_bin, byteorder='big')
        cksum = 0
        cksum ^= cksum_lookup[(device_id_int >> 28) & 0x0F]
        cksum ^= (device_id_int >> 24) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 20) & 0x0F]
        cksum ^= (device_id_int >> 16) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 12) & 0x0F]
        cksum ^= (device_id_int >> 8) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 4) & 0x0F]
        cksum ^= (device_id_int >> 0) & 0x0F
        return cksum == 0

    # given a device id, will adjust the last 4 bits to make it valid and return the integer value
    def hdhr_get_valid_device_id(self, device_id):
        hex_digits = set(string.hexdigits)
        if len(device_id) != 8:
            self.logger.error('ERROR: HDHR Device ID must be 8 hexadecimal values')
            return 0
        if not all(c in hex_digits for c in device_id):
            self.logger.error('ERROR: HDHR Device ID characters must all be hex (0-A)')
            return 0
        device_id_bin = bytes.fromhex(device_id)
        cksum_lookup = [0xA, 0x5, 0xF, 0x6, 0x7, 0xC, 0x1, 0xB, 0x9, 0x2, 0x8, 0xD, 0x4, 0x3, 0xE, 0x0]
        device_id_int = int.from_bytes(device_id_bin, byteorder='big')
        cksum = 0
        cksum ^= cksum_lookup[(device_id_int >> 28) & 0x0F]
        cksum ^= (device_id_int >> 24) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 20) & 0x0F]
        cksum ^= (device_id_int >> 16) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 12) & 0x0F]
        cksum ^= (device_id_int >> 8) & 0x0F
        cksum ^= cksum_lookup[(device_id_int >> 4) & 0x0F]
        new_dev_id = (device_id_int & 0xFFFFFFF0) + cksum
        return struct.pack('>I', new_dev_id).hex().upper()

    def hdhr_gen_device_id(self):
        baseid = '105' + ''.join(random.choice('0123456789ABCDEF') for i in range(4)) + '0'
        return self.hdhr_get_valid_device_id(baseid)

    # removes sensitive data from config and returns a copy
    def filter_config_data(self):
        filtered_config = copy.deepcopy(self.data)
        for module in list(self.defn_json.keys()):
            for section in list(self.defn_json[module]['sections'].keys()):
                for key, settings in list(self.defn_json[module]['sections'][section]['settings'].items()):
                    if settings['level'] == 4:
                        del filtered_config[section][key]
                    elif 'hidden' in settings and settings['hidden']:
                        del filtered_config[section][key]
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
                self.logger.debug('unknown value type for [{}][{}]  type is {}'
                    .format(section, key, type(self.data[section][key])))

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
                self.logger.debug('KeyError-2 [{}][{}]'.format(section, key))
                # no default, so assume using the string as is
                if self.data[section][key] != updated_data[section][key]:
                    updated_data[section][key].append(True)

    def update_config(self, updated_data):

        for area, area_data in self.defn_json.items():
            for section, section_data in area_data['sections'].items():
                if section not in updated_data:
                    updated_data[section]={}
                for setting, setting_data in section_data['settings'].items():
                    if setting_data['level'] == 4:
                        pass
                    elif 'writable' in setting_data and not setting_data['writable']:
                        if setting in updated_data[section]:
                            updated_data[section][setting].append(False)
                    elif 'hidden' in setting_data and setting_data['hidden'] \
                            and setting not in updated_data[section]:
                        pass
                    else:
                        self.detect_change(section, setting, updated_data)

        # save the changes to config.ini and self.data
        results = '<hr><h3>Status Results</h3><ul>'
        for key in updated_data.keys():
            results += self.save_config_section(key, updated_data)
        with open(self.data['main']['config_file'], 'w') as config_file:
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
                    self.data[section][key] \
                        = self.config_defaults[section][key]
                    self.logger.debug(
                        'Config Update: Removed [{}][{}]'.format(section, key))
                    results += \
                        '<li>Removed [{}][{}] from config.ini, using default value</li>' \
                        .format(section, key)
                else:
                    # set new value
                    self.logger.debug(
                        'Config Update: Changed [{}][{}] to {}'
                        .format(section, key, updated_data[section][key][0]))
                    try:
                        self.config_handler.set(
                            section, key, str(updated_data[section][key][0]))
                    except configparser.NoSectionError:
                        self.config_handler.add_section(section)
                        self.config_handler.set(
                            section, key, str(updated_data[section][key][0]))
                    self.data[section][key] = updated_data[section][key][0]
                    results += '<li>Updated [{}][{}] to {}</li>' \
                        .format(section, key, updated_data[section][key][0])
        return results

    def call_oninit(self):
        for module in list(self.defn_json.keys()):
            for section in list(self.defn_json[module]['sections'].keys()):
                for key, settings in list(self.defn_json[module]['sections'][section]['settings'].items()):
                    if 'onInit' in settings:
                        self.call_function(settings['onInit'])

    # We make the last adjustments here after super() updates
    def tvh_config_adjustments(self, opersystem, script_dir):

        self.call_oninit()

        if not self.data['main']['ffmpeg_path']:
            if opersystem in ['Windows']:
                base_ffmpeg_dir \
                    = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                self.data['main']['ffmpeg_path'] \
                    = pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe')
            else:
                self.data['main']['ffmpeg_path'] = 'ffmpeg'
        else:
            if not os.path.exists(self.data['main']['ffmpeg_path']):
                if opersystem in ['Windows']:
                    base_ffmpeg_dir \
                        = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                    self.data['main']['ffmpeg_path'] \
                        = pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe')
                else:
                    self.data['main']['ffmpeg_path'] = 'ffmpeg'

        if not self.data['player']['ffprobe_path']:
            if opersystem in ['Windows']:
                base_ffprobe_dir \
                    = pathlib.Path(script_dir).joinpath('ffmpeg/bin')
                self.data['player']['ffprobe_path'] \
                    = pathlib.Path(base_ffprobe_dir).joinpath('ffprobe.exe')
            else:
                self.data['player']['ffprobe_path'] = 'ffprobe'

        if self.data['main']['local_ip'] == '0.0.0.0':
            self.data["main"]['bind_ip'] = '0.0.0.0'
            self.data['main']['plex_accessible_ip'] \
                = self.get_ip()
        else:
            self.data['main']['bind_ip'] \
                = self.data['main']['local_ip']
            self.data['main']['plex_accessible_ip'] \
                = self.data['main']['local_ip']

        if self.data['hdhomerun']['hdhr_id'] is None:
            self.data['hdhomerun']['hdhr_id'] \
                = self.hdhr_gen_device_id()
            self.write(
                'hdhomerun', 'hdhr_id',
                self.data["hdhomerun"]['hdhr_id'])
        else:
            if not self.hdhr_validate_device_id(
                    self.data['hdhomerun']['hdhr_id']):
                self.data['hdhomerun']['hdhr_id'] \
                    = self.hdhr_gen_device_id()
                self.write(
                    'hdhomerun', 'hdhr_id',
                    self.data["hdhomerun"]['hdhr_id'])

        if len(self.data["main"]["uuid"]) < 32:
            self.data["main"]["uuid"] = str(uuid.uuid1()).upper()
            self.write('main', 'uuid', self.data["main"]["uuid"])

        # changing any types that cause issues with the JSON converter
        if type(self.data['main']['cache_dir']) is not str:
            self.data['main']['cache_dir'] \
                = str(self.data['main']['cache_dir'])
        if type(self.data['main']['ffmpeg_path']) is not str:
            print('FFMPEG NOT A STRING')
            self.data['main']['ffmpeg_path'] \
                = str(self.data['main']['ffmpeg_path'])
        if type(self.data['player']['ffprobe_path']) is not str:
            print('FFPROBE NOT A STRING')
            self.data['player']['ffprobe_path'] \
                = str(self.data['player']['ffprobe_path'])

        if CRYPTO_LOADED and self.data['main']['encrypt_key'] is None \
                and self.data['main']['use_encryption']:
            self.set_fernet_key()
            if self.data['main']['locast_password'].startswith(ENCRYPT_STRING):
                # encrypted
                self.data['main']['locast_password'] \
                    = self.decrypt(self.data['main']['locast_password'])
                if self.data['main']['locast_password'] == 'UNKNOWN':
                    self.logger.error(
                        'Unable to decrypt password. ' +
                        'Try updating password in config file to clear text')
            else:
                # not encrypted
                clear_pwd = self.data['main']['locast_password']
                encrypted_pwd = self.encrypt(
                    self.data['main']['locast_password'])
                self.write('main', 'locast_password', encrypted_pwd)
                self.data['main']['locast_password'] = clear_pwd

    # ###### ENCRYPTION SECTION #######

    def set_fernet_key(self):
        opersystem = platform.system()
        # is there a key already generated
        if opersystem in ['Windows']:
            key_file = os.getenv('LOCALAPPDATA') + '/.locast/key.txt'
        else:  # linux
            key_file = os.getenv('HOME') + '/.locast/key.txt'
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

    def decrypt(self, enc_str):
        if enc_str.startswith(ENCRYPT_STRING):
            f = Fernet(self.data['main']['encrypt_key'])
            try:
                token = f.decrypt(enc_str[len(ENCRYPT_STRING):].encode())
            except cryptography.fernet.InvalidToken:
                # occurs when multiple users are running the app.
                # need to signal the caller that we have issues
                self.logger.warning("Unable to decrypt string.")
                return 'UNKNOWN'

            return token.decode()
        else:
            return enc_str

    # ###### END ENCRYPTION SECTION #######

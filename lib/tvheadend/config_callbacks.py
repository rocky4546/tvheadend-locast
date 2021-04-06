import logging
import logging.config
import platform
import requests
import pathlib
import os
import uuid
import lib.tvheadend.utils as utils

try:
    import cryptography
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet
    CRYPTO_LOADED = True
except ImportError:
    CRYPTO_LOADED = False

ENCRYPT_STRING = 'ENC::'

def noop(config_obj, section, key):
    pass


def logging_refresh(config_obj, section, key):
    logging.config.fileConfig(fname=config_obj.config_file, disable_existing_loggers=False)
    resp = requests.get('http://{}:{}/logreset'.format(
        config_obj.data['main']['plex_accessible_ip'], str(config_obj.data['main']['plex_accessible_port'])))


def set_version(config_obj, section, key):
    config_obj.data['main']['reporting_firmware_ver'] \
            = 'v' + utils.get_version_str()


def set_data_path(config_obj, section, key):
    if not config_obj.data["paths"]["data_dir"]:
        config_obj.data["paths"]["data_dir"] = pathlib.Path(config_obj.data["paths"]["main_dir"]).joinpath('data')
    else:
        config_obj.data["paths"]["data_dir"] = pathlib.Path(config_obj.data["paths"]["data_dir"])
    if not os.path.exists(config_obj.data["paths"]["data_dir"]):
        config_obj.data["paths"]["data_dir"].mkdir()
    config_obj.data["paths"]["data_dir"]= str(os.path.abspath(config_obj.data["paths"]["data_dir"]))


def set_cache_path(config_obj, section, key):
    if not config_obj.data["paths"]["cache_dir"]:
        config_obj.data["paths"]["cache_dir"] = pathlib.Path(config_obj.data["paths"]["data_dir"]).joinpath('cache')
    else:
        config_obj.data["paths"]["cache_dir"] = pathlib.Path(config_obj.data["paths"]["cache_dir"])
    if not config_obj.data["paths"]["cache_dir"].is_dir():
        config_obj.data["paths"]["cache_dir"].mkdir()
    config_obj.data["paths"]["cache_dir"]= str(os.path.abspath(config_obj.data["paths"]["cache_dir"]))


def set_stations_path(config_obj, section, key):
    if not config_obj.data["paths"]["stations_dir"]:
        config_obj.data["paths"]["stations_dir"] = pathlib.Path(config_obj.data["paths"]["cache_dir"]).joinpath('stations')
    else:
        config_obj.data["paths"]["stations_dir"] = pathlib.Path(config_obj.data["paths"]["stations_dir"])
    if not config_obj.data["paths"]["stations_dir"].is_dir():
        config_obj.data["paths"]["stations_dir"].mkdir()
    config_obj.data["paths"]["stations_dir"]= str(os.path.abspath(config_obj.data["paths"]["stations_dir"]))


def set_configdefn_path(config_obj, section, key):
    config_obj.data['paths']['config_defn_dir'] = config_obj.config_defn_path

    
def set_main_path(config_obj, section, key):
    config_obj.data['paths']['main_dir'] = config_obj.script_dir


def set_ffmpeg_path(config_obj, section, key):
    if not config_obj.data['player']['ffmpeg_path'] and \
            config_obj.data['player']['stream_type'] == "ffmpegproxy":
        if platform.system() in ['Windows']:
            base_ffmpeg_dir \
                = pathlib.Path(config_obj.script_dir).joinpath('ffmpeg/bin')
            if base_ffmpeg_dir.is_dir():
                config_obj.data['player']['ffmpeg_path'] \
                    = str(pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe'))
            else:
                config_obj.logger.warning('ffmpeg_path does not exist and is required based on stream_type')
        else:
            config_obj.data['player']['ffmpeg_path'] = 'ffmpeg'


def set_ffprobe_path(config_obj, section, key):
    if not config_obj.data['player']['ffprobe_path'] and \
            config_obj.data['player']['stream_type'] == "ffmpegproxy":
        if platform.system() in ['Windows']:
            base_ffprobe_dir \
                = pathlib.Path(config_obj.script_dir).joinpath('ffmpeg/bin')
            config_obj.data['player']['ffprobe_path'] \
                = str(pathlib.Path(base_ffprobe_dir).joinpath('ffprobe.exe'))
            config_obj.logger.warning('ffprobe_path does not exist and is required based on stream_type')
        else:
            config_obj.data['player']['ffprobe_path'] = 'ffprobe'


def load_encrypted_setting(config_obj, section, key):
    if CRYPTO_LOADED and config_obj.data['main']['encrypt_key'] is None \
            and config_obj.data['main']['use_encryption']:
        config_obj.set_fernet_key()
        if config_obj.data[section][key].startswith(ENCRYPT_STRING):
            # encrypted
            config_obj.data[section][key] \
                = config_obj.decrypt(config_obj.data[section][key])
            if config_obj.data[section][key] == 'UNKNOWN':
                config_obj.logger.error(
                    'Unable to decrypt password. ' +
                    'Try updating password in config file in clear text')
        else:
            # not encrypted
            clear_pwd = config_obj.data[section][key]
            encrypted_pwd = config_obj.encrypt(
                config_obj.data[section][key])
            config_obj.write(section, key, encrypted_pwd)
            config_obj.data[section][key] = clear_pwd


def set_ip(config_obj, section, key):
    if config_obj.data[section][key] == '0.0.0.0':
        config_obj.data['main']['bind_ip'] = '0.0.0.0'
        config_obj.data['main']['plex_accessible_ip'] \
            = config_obj.get_ip()
    else:
        config_obj.data['main']['bind_ip'] \
            = config_obj.data[section][key]
        config_obj.data['main']['plex_accessible_ip'] \
            = config_obj.data[section][key]

def set_hdhomerun_id(config_obj, section, key):
    if config_obj.data['hdhomerun']['hdhr_id'] is None:
        config_obj.data['hdhomerun']['hdhr_id'] \
            = config_obj.hdhr_gen_device_id()
        config_obj.write(
            'hdhomerun', 'hdhr_id',
            config_obj.data["hdhomerun"]['hdhr_id'])
    else:
        if not config_obj.hdhr_validate_device_id(
                config_obj.data['hdhomerun']['hdhr_id']):
            config_obj.data['hdhomerun']['hdhr_id'] \
                = config_obj.hdhr_gen_device_id()
            config_obj.write(
                'hdhomerun', 'hdhr_id',
                config_obj.data["hdhomerun"]['hdhr_id'])


def set_uuid(config_obj, section, key):
    if config_obj.data["main"]["uuid"] is None:
        config_obj.data["main"]["uuid"] = str(uuid.uuid1()).upper()
        config_obj.write('main', 'uuid', config_obj.data["main"]["uuid"])


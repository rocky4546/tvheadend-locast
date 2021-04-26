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

import importlib
import logging
import logging.config
import platform
import requests
import pathlib
import os
import uuid
import lib.tvheadend.utils as utils
import lib.tvheadend.encryption as encryption
import lib.tvheadend.hdhr_server as hdhr_server

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


def call_function(_func_str, _section, _key, _config_obj):
    """ calls the function in the definition.  If relative path
        then assume module is relative to the plugins directory
    """
    mod_name, func_name = _func_str.rsplit('.', 1)
    if mod_name.startswith('.'):
        mod = importlib.import_module(
            mod_name,
            package=_config_obj.data['paths']['internal_plugins_pkg'])
    else:
        mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name)
    return func(_config_obj, _section, _key)


def noop(_config_obj, _section, _key):
    pass


def logging_refresh(_config_obj, _section, _key):
    logging.config.fileConfig(fname=_config_obj.data['paths']['config_file'], disable_existing_loggers=False)
    _resp = requests.get('http://{}:{}/logreset'.format(
        _config_obj.data['web']['plex_accessible_ip'], str(_config_obj.data['web']['plex_accessible_port'])))


def set_version(_config_obj, _section, _key):
    _config_obj.data[_section][_key] \
        = 'v' + utils.get_version_str()


def set_path(_config_obj, _section, _key, _base_dir, _folder):
    if not _config_obj.data[_section][_key]:
        _config_obj.data[_section][_key] = pathlib.Path(_base_dir).joinpath(_folder)
    else:
        _config_obj.data[_section][_key] = pathlib.Path(_config_obj.data[_section][_key])
    if not _config_obj.data[_section][_key].is_dir():
        _config_obj.data[_section][_key].mkdir()
    _config_obj.data[_section][_key] = str(os.path.abspath(_config_obj.data[_section][_key]))


def set_data_path(_config_obj, _section, _key):
    set_path(_config_obj, _section, _key,
        _config_obj.data["paths"]["main_dir"], 'data')


def set_cache_path(_config_obj, _section, _key):
    set_path(_config_obj, _section, _key,
        _config_obj.data["paths"]["data_dir"], 'cache')


def set_stations_path(_config_obj, _section, _key):
    set_path(_config_obj, _section, _key,
        _config_obj.data["paths"]["cache_dir"], 'stations')


def set_database_path(_config_obj, _section, _key):
    set_path(_config_obj, _section, _key,
        _config_obj.data["paths"]["data_dir"], 'db')


def set_configdefn_path(_config_obj, _section, _key):
    _config_obj.data['paths']['config_defn_pkg'] = _config_obj.defn_json.defn_path


def set_main_path(_config_obj, _section, _key):
    _config_obj.data['paths']['main_dir'] = _config_obj.script_dir


def set_ffmpeg_path(_config_obj, _section, _key):
    if not _config_obj.data[_section][_key]:
        if platform.system() in ['Windows']:
            base_ffmpeg_dir \
                = pathlib.Path(_config_obj.script_dir).joinpath('ffmpeg/bin')
            if base_ffmpeg_dir.is_dir():
                _config_obj.data[_section][_key] \
                    = str(pathlib.Path(base_ffmpeg_dir).joinpath('ffmpeg.exe'))
            else:
                _config_obj.logger \
                    .warning('player-ffmpeg_path does not exist and may be required based on player-stream_type')
        else:
            _config_obj.data[_section][_key] = 'ffmpeg'


def set_ffprobe_path(_config_obj, _section, _key):
    if not _config_obj.data[_section][_key]:
        if platform.system() in ['Windows']:
            base_ffprobe_dir \
                = pathlib.Path(_config_obj.script_dir).joinpath('ffmpeg/bin')
            _config_obj.data[_section][_key] \
                = str(pathlib.Path(base_ffprobe_dir).joinpath('ffprobe.exe'))
            _config_obj.logger.warning('ffprobe_path does not exist and may be required based on stream_type')
        else:
            _config_obj.data[_section][_key] = 'ffprobe'


def load_encrypted_setting(_config_obj, _section, _key):
    if CRYPTO_LOADED and _config_obj.data['main']['encrypt_key'] is None \
            and _config_obj.data['main']['use_encryption'] \
            and _config_obj.data[_section][_key] is not None:
        _config_obj.data['main']['encrypt_key'] = encryption.set_fernet_key().decode('utf-8')
        if _config_obj.data[_section][_key].startswith(ENCRYPT_STRING):
            # encrypted
            _config_obj.data[_section][_key] \
                = encryption.decrypt(
                _config_obj.data[_section][_key],
                _config_obj.data['main']['encrypt_key'])
            if _config_obj.data[_section][_key] is None:
                _config_obj.logger.error(
                    'Unable to decrypt password. ' +
                    'Try updating password in config file in clear text')
        else:
            # not encrypted
            clear_pwd = _config_obj.data[_section][_key]
            encrypted_pwd = encryption.encrypt(
                _config_obj.data[_section][_key],
                _config_obj.data['main']['encrypt_key'])
            _config_obj.write(_section, _key, encrypted_pwd)
            _config_obj.data[_section][_key] = clear_pwd


def set_ip(_config_obj, _section, _key):
    if _config_obj.data[_section][_key] == '0.0.0.0':
        _config_obj.data['web']['bind_ip'] = '0.0.0.0'
        _config_obj.data['web']['plex_accessible_ip'] \
            = utils.get_ip()
    else:
        _config_obj.data['web']['bind_ip'] \
            = _config_obj.data[_section][_key]
        _config_obj.data['web']['plex_accessible_ip'] \
            = _config_obj.data[_section][_key]


def set_hdhomerun_id(_config_obj, _section, _key):
    if _config_obj.data['hdhomerun']['hdhr_id'] is None:
        _config_obj.data['hdhomerun']['hdhr_id'] \
            = hdhr_server.hdhr_gen_device_id()
        _config_obj.write(
            'hdhomerun', 'hdhr_id',
            _config_obj.data["hdhomerun"]['hdhr_id'])
    else:
        if not hdhr_server.hdhr_validate_device_id(
                _config_obj.data['hdhomerun']['hdhr_id']):
            _config_obj.data['hdhomerun']['hdhr_id'] \
                = hdhr_server.hdhr_gen_device_id()
            _config_obj.write(
                'hdhomerun', 'hdhr_id',
                _config_obj.data["hdhomerun"]['hdhr_id'])


def set_uuid(_config_obj, _section, _key):
    if _config_obj.data["main"]["uuid"] is None:
        _config_obj.data["main"]["uuid"] = str(uuid.uuid1()).upper()
        _config_obj.write('main', 'uuid', _config_obj.data["main"]["uuid"])


def check_value_4(_config_obj, _section, _key):
    value = _config_obj.data[_section][_key]
    if not 1 <= value <= 4:
        _config_obj.data[_section][_key] = 4

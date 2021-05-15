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

import datetime
import glob
import logging
import logging.config
import mimetypes
import ntpath
import os
import pathlib
import shutil
import socket
import struct
import sys

import lib.common.exceptions as exceptions

VERSION = '0.8.4'
CABERNET_URL = 'https://github.com/rocky4546/tvheadend-locast'
CABERNET_NAME = 'cabernet'


def get_version_str():
    return VERSION


def logging_setup(_config_paths):
    if os.environ.get('LOGS_DIR') is None:
        if _config_paths['logs_dir'] is not None:        
            os.environ['LOGS_DIR'] = _config_paths['logs_dir']
            logging.config.fileConfig(fname=_config_paths['config_file'])
        elif not os.path.isdir('data/logs'):
            os.makedirs('data/logs')
    if str(logging.getLevelName('NOTUSED')).startswith('Level'):
        logging.config.fileConfig(fname=_config_paths['config_file'])
        logging.addLevelName(100, 'NOTUSED')


def clean_exit(exit_code=0):
    sys.stderr.flush()
    sys.stdout.flush()
    sys.exit(exit_code)


def block_print():
    sys.stdout = open(os.devnull, 'w')


def enable_print():
    sys.stdout = sys.__stdout__


def str2bool(s):
    return str(s).lower() in ['true', '1', 'yes', 'on']


def tm_parse(tm):
    tm_date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=tm / 1000)
    tm = str(tm_date.strftime('%Y%m%d%H%M%S +0000'))
    return tm


def date_parse(date_secs, format_str):
    if not date_secs:
        return date_secs
    dt_date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=date_secs / 1000)
    dt_str = str(dt_date.strftime(format_str))
    return dt_str


def is_file_expired(filepath, days=0, hours=0):
    if not os.path.exists(filepath):
        return True
    current_time = datetime.datetime.utcnow()
    file_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(filepath))
    if days == 0:
        if int((current_time - file_time).total_seconds() / 3600) > hours:
            return True
    elif (current_time - file_time).days > days:
        return True
    return False


def merge_dict(d1, d2, override=False, ignore_conflicts=False):
    for key in d2:
        if key in d1:
            if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                merge_dict(d1[key], d2[key], override, ignore_conflicts)
            elif d1[key] == d2[key]:
                pass
            elif override:
                d1[key] = d2[key]
            elif not ignore_conflicts:
                raise exceptions.CabernetException('Conflict when merging dictionaries {}'.format(str(key)))
        else:
            d1[key] = d2[key]
    return d1


def get_ip():
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


def wrap_chnum(_chnum, _namespace, _instance, _config):
    """
    Adds prefix and suffix to chnum.  If prefix is a integer, then
    will add the prefix to the chnum instead of using it like a string.
    """
    inst_config_sect = instance_config_section(_namespace, _instance)
    prefix = _config[inst_config_sect]['epg-prefix']
    suffix = _config[inst_config_sect]['epg-suffix']
    if prefix is None:
        prefix = ""
    if suffix is None:
        suffix = ""
    try:
        ch_int = int(prefix)
        ch_split = _chnum.split('.', 1)
        ch_int += int(ch_split[0])
        if len(ch_split) == 2:
            ch_str = str(ch_int) + '.' + ch_split[1]
        else:
            ch_str = str(ch_int)
    except ValueError:
        ch_str = prefix + _chnum
    ch_str += suffix
    return ch_str


def instance_config_section(_namespace, _instance):
    return _namespace.lower() + '_' + _instance


def process_image_url(_config, _thumbnail_url):
    if _thumbnail_url.startswith('file://'):
        filename = ntpath.basename(_thumbnail_url)
        mime_lookup = mimetypes.guess_type(filename)
        new_filename = filename.replace(' ','')
        if mime_lookup[0] is not None and \
                mime_lookup[0].startswith('image'):
            old_path = _thumbnail_url.replace('file://', '')
            new_path = pathlib.Path(_config['paths']['main_dir']) \
                .joinpath('lib/web/htdocs/temp') \
                .joinpath(new_filename)
            if not new_path.exists():
                try:
                    shutil.copyfile(old_path, new_path)
                except OSError:
                    # windows path exception.  remove '/'
                    try:
                        shutil.copyfile(old_path[1:], new_path)                
                    except FileNotFoundError:
                        logger = logging.getLogger(__name__)
                        logger.warning('Image file not found: {}'.format(old_path))
                        return '/temp/FILENOTFOUND'
                except FileNotFoundError:
                    logger = logging.getLogger(__name__)
                    logger.warning('Image file not found: {}'.format(old_path))
                    return '/temp/FILENOTFOUND'
            return '/temp/'+new_filename
        else:
            return '/temp/NOTANIMAGE'
    else:
        return _thumbnail_url

def cleanup_web_temp(_config):
    dir = _config['paths']['main_dir']
    filelist = glob.glob(os.path.join(dir, 'lib', 'web', 'htdocs', 'temp', '[!__]*'))
    for f in filelist:
        if os.path.isfile(f):
            os.remove(f)

# BYTE METHODS

def set_u8(integer):
    return struct.pack('B', integer)


def set_u16(integer):
    return struct.pack('>H', integer)


def set_u32(integer):
    return struct.pack('>I', integer)


def set_u64(integer):
    return struct.pack('>Q', integer)


# HDHR requires a null byte at the end most of the time
def set_str(string, add_null):
    # places the length in a single byte, the string and then a null byte if add_null is true
    if add_null:
        return struct.pack('B%dsB' % (len(string)), len(string) + 1, string, 0)
    else:
        return struct.pack('B%ds' % (len(string)), len(string), string)

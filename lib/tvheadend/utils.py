import os
import sys
import struct
import logging
import logging.config
import datetime


VERSION = '0.7.5'
MAIN_DIR = None

def get_version_str():
    return VERSION


def logging_setup(config_file):
    if str(logging.getLevelName('NOTUSED')).startswith('Level'):
        logging.config.fileConfig(fname=config_file)
        logging.addLevelName(100, 'NOTUSED')


def logging_refresh(config_obj):
    logging.config.fileConfig(fname=config_obj.config_file)

def noop(config_obj):
    pass

def set_version(config_obj):
    config_obj.data['main']['reporting_firmware_ver'] \
            = 'v' + get_version_str()

def block_print():
    sys.stdout = open(os.devnull, 'w')


def enable_print():
    sys.stdout = sys.__stdout__

    
def str2bool(s):
    return str(s).lower() in ['true', '1', 'yes', 'on']



def tm_parse(tm):
    tm_date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=tm/1000)
    tm = str(tm_date.strftime('%Y%m%d%H%M%S +0000'))
    return tm


def is_file_expired(filepath, days=0, hours=0):
    if not os.path.exists(filepath):
        return True
    current_time = datetime.datetime.utcnow()
    file_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(filepath))
    if days == 0:
        if int((current_time - file_time).total_seconds()/3600) > hours:
            return True
    elif (current_time - file_time).days > days:
        return True
    return False


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
        return struct.pack('B%dsB' % (len(string)), len(string)+1, string, 0)
    else:
        return struct.pack('B%ds' % (len(string)), len(string), string)

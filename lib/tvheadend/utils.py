import os
import sys
import struct
import logging
import logging.config
import datetime

VERSION = '0.7.3-RC2'

def get_version_str():
    return VERSION


def logging_setup(config_file):
    logging.config.fileConfig(fname=config_file)


def logging_refresh(configObj):
    logging.config.fileConfig(fname=configObj.config_file)


def block_print():
    sys.stdout = open(os.devnull, 'w')


def enable_print():
    sys.stdout = sys.__stdout__

    
def str2bool(s):
    # on is from html form checkbox when selected
    return str(s).lower() in ['true', '1', 'yes', 'on']


def gen_fernet_key(self, user_key):
    key = user_key
    if not user_key.startswith(ENCRYPT_STRING):
        str_bytes = user_key.encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'!@#$oixcvjmrteq',
            iterations=100000,
            backend=default_backend()
        )
        key_bytes = base64.urlsafe_b64encode(kdf.derive(str_bytes))
        key = key_bytes.decode()
        print('string=', user_key, 'key_bytes=', key_bytes, 'key=', key)
    return key_bytes

        
def noop(configObj):
    pass


def tm_parse(tm):
    tm_date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=tm/1000)
    #tm = datetime.datetime.utcfromtimestamp(tm/1000.0) #does not work before 1970
    tm = str(tm_date.strftime('%Y%m%d%H%M%S +0000'))
    return tm



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
        return struct.pack('B%dsB' % (len(string)), len(string)+1,string,0)
    else:
        return struct.pack('B%ds' % (len(string)), len(string),string)
    
    

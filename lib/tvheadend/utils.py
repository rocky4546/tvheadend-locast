import os
import sys
import logging
import logging.config

VERSION = '0.7.2'

def get_version_str():
    return VERSION


def logging_setup(config_file):
    logging.config.fileConfig(fname='config.ini')


def block_print():
    sys.stdout = open(os.devnull, 'w')


def enable_print():
    sys.stdout = sys.__stdout__

    
def str2bool(string):
    return str(string).lower() in ('yes', 'true')


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

        
            

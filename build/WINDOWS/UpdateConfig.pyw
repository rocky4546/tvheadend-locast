#!/usr/bin/env python
""" calls the main rountine running in the tvheadend folder """
import os
import pip
import sys
import argparse
import platform
import pathlib
import base64
import binascii
import logging

try:
    import cryptography
except ImportError:
    pip.main(['install', 'cryptography']) 

from lib.tvheadend.user_config import get_config


def get_args():
    parser = argparse.ArgumentParser(description='Fetch TV from locast.', epilog='')
    parser.add_argument('--installdir', dest='instdir', type=str, default=None, help='', required=True)
    parser.add_argument('--username', dest='user', type=str, default=None, help='', required=True)
    parser.add_argument('--password', dest='pwd', type=str, default=None, help='', required=True)
    parser.add_argument('--configfile', dest='cfg', type=str, default=None, help='')
    return parser.parse_args()



# Startup Logic
if __name__ == '__main__':
    #os.chdir(os.path.dirname(os.path.abspath(__file__)))
    script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    opersystem = platform.system()

    args = get_args()

    # determine if a config.ini file exists at the top folder of the install
    # if not found, use the example config file
    # otherwise, update currect config.ini with the new user/pwd info
    install_dir = pathlib.Path(os.path.abspath(str(args.instdir)))
    if not os.path.exists(install_dir):
        print("ERROR: installdir not found at ", install_dir)
        sys.exit(1)
    config_file = pathlib.Path(install_dir).joinpath("config.ini")
    print(install_dir)

    if os.path.exists(config_file):
        print("configfile found at ", config_file)
        args.cfg = config_file
        # update current config.ini file
    else:
        print("configfile not found at ", config_file)
        # find the examples config file
        config_ex_file = pathlib.Path(install_dir).joinpath("lib/tvheadend/config_example.ini")
        if os.path.exists(config_ex_file):
            print("config example file found at ", config_ex_file)
            args.cfg = config_ex_file
        else:
            print("ERROR: config example file not found at ", config_ex_file)
            sys.exit(1)

    print("args.cfg=", args.cfg)

    configObj = get_config(install_dir, opersystem, args)

    if configObj.data['main']['locast_password'] == 'UNKNOWN':
        #  two different users trying to decrypt the encrypted password
        #  ignore the error and update with password passed in
        logging.info('ignoring password error and ' \
            + 'replacing password with one provided by user')

    base64_bytes = args.pwd.encode('ascii')
    try:
        message_bytes = base64.b64decode(base64_bytes)
    except binascii.Error:
        # assume password is not base 64 encoded
        message_bytes = base64_bytes
        pass
        
    message = message_bytes.decode('ascii')
    pwd = message
    print("user=", args.user,
          "pwd=", pwd)

    # update config object
    configObj.data["main"]["locast_username"] = args.user
    configObj.config_handler.set("main", "locast_username", args.user)
    configObj.data["main"]["locast_password"] = pwd
    configObj.config_handler.set("main", "locast_password", pwd)

    with open(config_file, 'w') as config_fileptr:
        configObj.config_handler.write(config_fileptr)

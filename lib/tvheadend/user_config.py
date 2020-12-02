import os
import random
import configparser
import pathlib

import lib.user_config


def get_config(script_dir, opersystem, args):
    return TVHUserConfig(script_dir, opersystem, args).data


class TVHUserConfig( lib.user_config.UserConfig ):

    def __init__(self, script_dir, opersystem, args):
        self.data["main"].update({
            'free_refresh_rate': 824,  #CAM   should be less than 15 minutes in seconds
            'is_free_account': True,  #CAM automatically internally set
            'servicename_prefix': "", #CAM prefix added to the channel number associated with the service name
            'servicename_suffix': "", #CAM suffix added to the channel number associated with the service name
        })
        super().__init__(script_dir, opersystem, args)


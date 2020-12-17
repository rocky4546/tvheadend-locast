import os
import sys
import logging
import logging.config

def get_version_str():
    return '0.7.1'

def logging_setup(config_file):
    logging.config.fileConfig(fname='config.ini')
    logger = logging.getLogger('root')

def block_print():
    sys.stdout = open(os.devnull, 'w')

def enable_print():
    sys.stdout = sys.__stdout__
    
def str2bool(string):
    return str(string).lower() in ("yes", "true")
    
    
    
def info(msg, *args, **kwargs):
    if len(root.handlers) == 0:
        basicConfig()
    root.info(msg, *args, **kwargs)

def debug(msg, *args, **kwargs):
    if len(root.handlers) == 0:
        basicConfig()
    root.debug(msg, *args, **kwargs)

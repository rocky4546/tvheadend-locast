#!/usr/bin/env python3
import os
import sys

if sys.version_info.major == 2 or sys.version_info < (3, 7):
    print('Error: cabernet requires python 3.7+.')
    sys.exit(1)

from lib import main

if __name__ == '__main__':
    #os.chdir(os.path.dirname(os.path.abspath(__file__)))
    #script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    script_dir = os.getcwd()
    main.main(script_dir)

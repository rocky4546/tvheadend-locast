#!/usr/bin/env python3
import os
import sys
from inspect import getsourcefile

if sys.version_info.major == 2 or sys.version_info < (3, 7):
    print('Error: cabernet requires python 3.7+.')
    sys.exit(1)

from lib import main

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    #script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    #print('os.path.realpath', os.path.realpath(__file__))
    #print('os.path.abspath(os.path.dirname',os.path.abspath(os.path.dirname(__file__)))
    #print('os.path.dirname',os.path.dirname(sys.argv[0]))
    #print('os.getcwd()', os.getcwd())
    #print('getsourcefile', os.path.abspath(os.path.dirname(getsourcefile(lambda:0))))
    script_dir = os.path.abspath(os.path.dirname(getsourcefile(lambda:0)))
    main.main(script_dir)

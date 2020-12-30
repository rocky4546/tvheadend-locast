#!/usr/bin/env python3
""" calls the main rountine running in the tvheadend folder """
import os
import pathlib
from lib.tvheadend import main

# Startup Logic
if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    script_dir = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
    main.main(script_dir)

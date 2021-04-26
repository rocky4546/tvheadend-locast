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

import json
import logging
import urllib
import urllib.error
import requests
from functools import update_wrapper


def handle_url_except(f):
    def wrapper_func(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except requests.exceptions.SSLError as sslError:
            logger = logging.getLogger(f.__name__)
            logger.error("SSLError in function {}(): {}".format(f.__name__, str(str(sslError))))
            return None
        except (urllib.error.HTTPError, requests.exceptions.HTTPError) as httpError:
            logger = logging.getLogger(f.__name__)
            logger.error("HTTPError in function {}(): {}".format(f.__name__, str(str(httpError))))
            return None
        except urllib.error.URLError as urlError:
            logger = logging.getLogger(f.__name__)
            logger.error("URLError in function {}(): {}".format(f.__name__, str(str(urlError))))
            return None
    return update_wrapper(wrapper_func, f)


def handle_json_except(f):
    def wrapper_func(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except json.JSONDecodeError as jsonError:
            logger = logging.getLogger(f.__name__)
            logger.error("JSONError in function {}(): {}".format(f.__name__, str(jsonError.reason)))
            return None
    return update_wrapper(wrapper_func, f)

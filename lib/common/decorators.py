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
from functools import update_wrapper


def handle_url_except(f):
    def wrapper_func(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except urllib.error.HTTPError as httpError:
            logger = logging.getLogger(f.__name__)
            logger.error("HTTPError in function {}(): {}".format(f.__name__, str(httpError)))
            return None
        except urllib.error.URLError as urlError:
            logger = logging.getLogger(f.__name__)
            logger.error("URLError in function {}(): {}".format(f.__name__, str(urlError)))
            return None
    return update_wrapper(wrapper_func, f)


def handle_json_except(f):
    def wrapper_func(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except json.JSONDecodeError as jsonError:
            logger = logging.getLogger(f.__name__)
            logger.error("JSONError in function {}(): {}".format(f.__name__, str(jsonError)))
            return None
    return update_wrapper(wrapper_func, f)


class Request:
    """
    Adds urls to functions for GET and POST methods
    """
    
    def __init__(self):
        self.url2func = {}
        self.method = None

    def route(self, *pattern):
        def wrap(func):
            for p in pattern:
                self.url2func[p] = func
            return func
        return wrap

    def log_urls(self):
        logger = logging.getLogger(__name__)
        for name in self.url2func.keys():
            logger.debug('Registering {} URL: {}'.format(self.method, name))

    def call_url(self, _tuner, _name, *args, **kwargs):
        if _name in self.url2func:
            self.url2func[_name](_tuner, *args, **kwargs)
            return True
        else:
            return False


class GetRequest(Request):

    def __init__(self):
        super().__init__()
        self.method = 'GET'

    
class PostRequest(Request):

    def __init__(self):
        super().__init__()
        self.method = 'POST'


class FileRequest(Request):
    """
    Adds HTDOCS areas to be processed by function
    """

    def __init__(self):
        super().__init__()
        self.method = 'GET'

    def call_url(self, _tuner, _name, *args, **kwargs):
        for key in self.url2func.keys():
            if _name.startswith(key):
                self.url2func[key](_tuner, *args, **kwargs)
                return True
        return False


getrequest = GetRequest()
postrequest = PostRequest()
filerequest = FileRequest()
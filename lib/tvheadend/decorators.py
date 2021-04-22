import json
import urllib
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
        except urllib.error.HTTPError as httpError:
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
        except json.JSONDecodeError as jsonError:
            logger = logging.getLogger(f.__name__)
            logger.error("JSONError in function {}(): {}".format(f.__name__, str(httpError.reason)))
            return None
    return update_wrapper(wrapper_func, f)

import lib.plugins.plugin as plugin
from .lib.locast import Locast


# register the init plugin function
@plugin.register
def start(config, namespace):
    return Locast(config, namespace)
    
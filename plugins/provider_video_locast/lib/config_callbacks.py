
from .channels import Channels
from lib.plugins.plugin_handler import PluginHandler

def force_channelsdb_refresh(_config_obj, _section, _key):
    locast_obj = PluginHandler.plugins['Locast'].plugin_obj
    locast_obj.channels.refresh_channels(True)

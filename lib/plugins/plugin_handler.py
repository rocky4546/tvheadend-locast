import logging
import json
import importlib
from importlib import resources

from .plugin import Plugin

PLUGIN_DEFN_FILE = 'plugin_defn.json'


class PluginHandler:

    def __init__(self, _config_obj):
        self.config_obj = _config_obj
        self.plugins = {}
        self.logger = logging.getLogger(__name__)
        self.plugin_defn = self.load_plugin_defn()
        self.collect_plugins(self.config_obj.data['paths']['internal_plugins_pkg'])

    def collect_plugins(self, _plugins_pkg):
        for folder in importlib.resources.contents(_plugins_pkg):
            if folder.startswith('__'):
                continue
            try:
                importlib.resources.read_text(_plugins_pkg, folder)
            except (IsADirectoryError, PermissionError):
                plugin = Plugin(self.config_obj, self.plugin_defn, '.'.join([_plugins_pkg, folder]))
                self.plugins[plugin.name] = plugin

    def load_plugin_defn(self):
        try:
            defn_file = importlib.resources.read_text(self.config_obj.data['paths']['resources_pkg'], PLUGIN_DEFN_FILE)
            self.logger.debug('Plugin Defn file loaded')
            defn = json.loads(defn_file)
        except FileNotFoundError:
            self.logger.warning('PLUGIN DEFN FILE NOT FOUND AT {} {}'.format(
                self.config_obj.data['paths']['resources_dir'], PLUGIN_DEFN_FILE))
            defn = {}
        return defn

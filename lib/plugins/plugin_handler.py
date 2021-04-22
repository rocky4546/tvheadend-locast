import logging
import json
import importlib

import lib.tvheadend.exceptions as exceptions

from .plugin import Plugin
from lib.db.db_plugins import DBPlugins

PLUGIN_DEFN_FILE = 'plugin_defn.json'


class PluginHandler:

    def __init__(self, _config_obj):
        self.config_obj = _config_obj
        self.plugins = {}
        self.logger = logging.getLogger(__name__)
        self.plugin_defn = self.load_plugin_defn()
        self.collect_plugins(self.config_obj.data['paths']['internal_plugins_pkg'])

    def collect_plugins(self, _plugins_pkg):
        plugin_db = DBPlugins(self.config_obj.data)
        plugin_db.set_updated(False)
        for folder in importlib.resources.contents(_plugins_pkg):
            if folder.startswith('__'):
                continue
            try:
                importlib.resources.read_text(_plugins_pkg, folder)
            except (IsADirectoryError, PermissionError):
                plugin = Plugin(self.config_obj, self.plugin_defn, '.'.join([_plugins_pkg, folder]))
                self.plugins[plugin.name] = plugin
        plugin_db.del_not_updated()
        

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

    def initialize_plugins(self):
        for name, plugin in self.plugins.items():
            try:
                plugin.plugin_obj = plugin.init_func(self.config_obj.data, plugin.namespace)
            except exceptions.CabernetException:
                self.logger.debug('Setting plugin {} to disabled'.format(plugin.name))
                plugin.enabled = False

    def refresh_channels(self):
        for name, plugin in self.plugins.items():
            try:
                if hasattr(plugin.plugin_obj, 'refresh_channels'):
                    plugin.plugin_obj.refresh_channels()
            except exceptions.CabernetException:
                self.logger.debug('Setting plugin {} to disabled'.format(plugin.name))
                plugin.enabled = False

    def refresh_epg(self, _namespace=None, _instance=None):
        if _namespace:
            if _namespace in self.plugins:
                self.plugins[_namespace].plugin_obj.refresh_epg(_instance)
        else:
            for name, plugin in self.plugins.items():
                try:
                    if hasattr(plugin.plugin_obj, 'refresh_epg'):
                        plugin.plugin_obj.refresh_epg()
                except exceptions.CabernetException:
                    self.logger.debug('Setting plugin {} to disabled'.format(plugin.name))
                    plugin.enabled = False

        
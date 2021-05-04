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

import logging
import json
import importlib
import importlib.resources

import lib.common.exceptions as exceptions

from .plugin import Plugin
from lib.db.db_plugins import DBPlugins

PLUGIN_DEFN_FILE = 'plugin_defn.json'


class PluginHandler:

    logger = None


    def __init__(self, _config_obj):
        self.plugins = {}
        self.config_obj = _config_obj
        if PluginHandler.logger is None:
            PluginHandler.logger = logging.getLogger(__name__)
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
                plugin.plugin_obj = plugin.init_func(self.config_obj, plugin.namespace)
            except exceptions.CabernetException:
                self.logger.debug('Setting plugin {} to disabled'.format(plugin.name))
                plugin.enabled = False

    def refresh_channels(self, _namespace=None):
        if _namespace is not None:
            plugin_obj = self.plugins[_namespace].plugin_obj
            try:
                if hasattr(plugin_obj, 'refresh_channels'):
                    plugin_obj.refresh_channels()
            except exceptions.CabernetException:
                self.logger.debug('Setting plugin {} to disabled'.format(_namespace))
                self.plugins[_namespace].enabled = False
        else:
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


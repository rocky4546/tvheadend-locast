import logging
import json
import importlib
from importlib import resources

import lib.tvheadend.utils as utils

from lib.config.config_defn import ConfigDefn

PLUGIN_CONFIG_DEFN_FILE = 'config_defn.json'
PLUGIN_MANIFEST_FILE = 'plugin.json'


class Plugin:

    def __init__(self, _config_obj, _plugin_defn, _plugin_pkg):
        self.plugin_pkg = _plugin_pkg
        self.config_obj = _config_obj
        self.logger = logging.getLogger(__name__)
        self.load_config_defn()
        self.plugin_settings = {}
        self.load_plugin_manifest(_plugin_defn)
        self.logger.info('Plugin created for {}'.format(self.name))

    def load_config_defn(self):
        try:
            self.logger.debug(
                'Plugin Config Defn file loaded at {}'.format(self.plugin_pkg))
            defn_obj = ConfigDefn(self.plugin_pkg, PLUGIN_CONFIG_DEFN_FILE, self.config_obj.data)
            default_config = defn_obj.get_default_config()
            self.config_obj.merge_config(default_config)
            defn_obj.call_oninit(self.config_obj)
            self.config_obj.defn_json.merge_defn_obj(defn_obj)

        except FileNotFoundError:
            self.logger.warning(
                'PLUGIN CONFIG DEFN FILE NOT FOUND AT {}'.format(self.plugin_pkg))

    def load_plugin_manifest(self, _plugin_defn):
        self.load_default_settings(_plugin_defn)
        self.import_manifest()

    def load_default_settings(self, _plugin_defn):
        for name, attr in _plugin_defn.items():
            self.plugin_settings[name] = attr['default']

    def import_manifest(self):
        try:
            json_settings = importlib.resources.read_text(self.plugin_pkg, PLUGIN_MANIFEST_FILE)
            settings = json.loads(json_settings)
            self.logger.debug(
                'Plugin Manifest file loaded at {}'.format(self.plugin_pkg))
            self.plugin_settings = utils.merge_dict(self.plugin_settings, settings, True)
        except FileNotFoundError:
            self.logger.warning(
                'PLUGIN MANIFEST FILE NOT FOUND AT {}'.format(self.plugin_pkg))

    @property
    def name(self):
        return self.plugin_settings['name']

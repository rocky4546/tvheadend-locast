import logging
import json
import importlib

import lib.tvheadend.utils as utils

from lib.config.config_defn import ConfigDefn
from lib.db.db_plugins import DBPlugins


PLUGIN_CONFIG_DEFN_FILE = 'config_defn.json'
PLUGIN_MANIFEST_FILE = 'plugin.json'

def register(func):
    """Decorator for registering a new plugin"""
    Plugin._plugin_func = func
    return func

class Plugin:

    # Temporarily used to register the plugin setup() function
    _plugin_func = None

    def __init__(self, _config_obj, _plugin_defn, _plugin_path):
        self.enabled = True
        self.plugin_path = _plugin_path
        self.config_obj = _config_obj
        self.logger = logging.getLogger(__name__)
        self.load_config_defn()

        # plugin is registered after this call, so grab reg data
        self.init_func = Plugin._plugin_func
        self.plugin_settings = {}
        self.plugin_db = DBPlugins(_config_obj.data)
        self.namespace = None
        self.instances = []
        self.load_plugin_manifest(_plugin_defn)
        self.logger.info('Plugin created for {}'.format(self.name))
        self.plugin_obj = None

        # describing instances????
        # first they will need configuration info from the config file for each instance
        # then they will also need to have some idea in the plugin that they exist
        # without a lot of issues
        # for now, we will assume all plugins are singletons with the instance name = 'Default'
        # config file can use an array format '_#' to id the different instances within
        # a namespace

    def load_config_defn(self):
        try:
            self.logger.debug(
                'Plugin Config Defn file loaded at {}'.format(self.plugin_path))
            defn_obj = ConfigDefn(self.plugin_path, PLUGIN_CONFIG_DEFN_FILE, self.config_obj.data)
            default_config = defn_obj.get_default_config()
            self.config_obj.merge_config(default_config)
            defn_obj.call_oninit(self.config_obj)
            self.config_obj.defn_json.merge_defn_obj(defn_obj)
            for area, area_data in defn_obj.config_defn.items():
                for section, section_data in area_data['sections'].items():
                    for setting in section_data['settings'].keys():
                        new_value = self.config_obj.fix_value_type(section, setting, self.config_obj.data[section][setting])
                        self.config_obj.data[section][setting] = new_value
            defn_obj.terminate()
        except FileNotFoundError:
            self.logger.warning(
                'PLUGIN CONFIG DEFN FILE NOT FOUND AT {}'.format(self.plugin_path))

    def load_plugin_manifest(self, _plugin_defn):
        self.load_default_settings(_plugin_defn)
        self.import_manifest()

    def load_default_settings(self, _plugin_defn):
        for name, attr in _plugin_defn.items():
            self.plugin_settings[name] = attr['default']

    def import_manifest(self):
        try:
            json_settings = importlib.resources.read_text(self.plugin_path, PLUGIN_MANIFEST_FILE)
            settings = json.loads(json_settings)
            self.namespace = settings['name']
            self.instances = ['Default']
            self.plugin_db.save_plugin(settings)
            self.plugin_db.save_instance(self.namespace, self.instances[0], '')
            self.logger.debug(
                'Plugin Manifest file loaded at {}'.format(self.plugin_path))
            self.plugin_settings = utils.merge_dict(self.plugin_settings, settings, True)
        except FileNotFoundError:
            self.logger.warning(
                'PLUGIN MANIFEST FILE NOT FOUND AT {}'.format(self.plugin_path))

    @property
    def name(self):
        return self.plugin_settings['name']

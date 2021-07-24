"""
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

import json
import threading

from lib.db.db import DB
from lib.common.decorators import Backup
from lib.common.decorators import Restore


DB_PLUGINS_TABLE = 'plugins'
DB_INSTANCE_TABLE = 'instance'
DB_CONFIG_NAME = 'db_files-plugins_db'


sqlcmds = {
    'ct': [
        """
        CREATE TABLE IF NOT EXISTS plugins (
            id        VARCHAR(255) NOT NULL PRIMARY KEY,
            namespace VARCHAR(255) NOT NULL UNIQUE,
            json TEXT NOT NULL
            )
        """,
        """
        CREATE TABLE IF NOT EXISTS instance (
            namespace VARCHAR(255) NOT NULL,
            instance  VARCHAR(255) NOT NULL,
            description TEXT,
            UNIQUE(namespace, instance)
            )
        """
    ],
    'dt': [
        """
        DROP TABLE IF EXISTS plugins
        """,
        """
        DROP TABLE IF EXISTS instance
        """
        ],

    'plugins_add':
        """
        INSERT OR REPLACE INTO plugins (
            id, namespace, json
            ) VALUES ( ?, ?, ? )
        """,
    'plugins_get':
        """
        SELECT * FROM plugins WHERE namespace=?
        """,


    'instance_add':
        """
        INSERT OR REPLACE INTO instance (
            namespace, instance, description
            ) VALUES ( ?, ?, ? )
        """,
    'instance_get':
        """
        SELECT * FROM instance ORDER BY namespace, instance
        """
}


class DBPlugins(DB):

    def __init__(self, _config):
        super().__init__(_config, _config['datamgmt'][DB_CONFIG_NAME], sqlcmds)

    def save_plugin(self, _plugin_dict):
        self.add(DB_PLUGINS_TABLE, (
            _plugin_dict['id'],
            _plugin_dict['name'],
            json.dumps(_plugin_dict)))

    def save_instance(self, namespace, instance, descr):
        self.add(DB_INSTANCE_TABLE, (
            namespace,
            instance,
            descr))

    def get_plugin(self, _namespace):
        rows = self.get_dict(DB_PLUGINS_TABLE, (_namespace,))
        for row in rows:
            return json.loads(row['json'])
        return None

    def get_instances(self):
        """
        createa a dict of namespaces that contain an array of instances
        """
        rows_dict = {}
        rows = self.get_dict(DB_INSTANCE_TABLE)
        for row in rows:
            if row['namespace'] not in rows_dict:
                rows_dict[row['namespace']] = []
            instances = rows_dict[row['namespace']]
            instances.append(row['instance'])
            # rows_dict[row['namespace']] = row['instance']

        return rows_dict

    def get_instances_full(self):
        rows_dict = {}
        rows = self.get_dict(DB_INSTANCE_TABLE)
        for row in rows:
            rows_dict[row['namespace']] = row
        return rows_dict

    @Backup(DB_CONFIG_NAME)
    def backup(self, backup_folder):
        self.export_sql(backup_folder)

    @Restore(DB_CONFIG_NAME)
    def restore(self, backup_folder):
        msg = self.import_sql(backup_folder)
        if msg is None:
            return 'Plugin Manifest Database Restored'
        else:
            return msg

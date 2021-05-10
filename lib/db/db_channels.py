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
import datetime
import sqlite3

from lib.db.db import DB

DB_CHANNELS_TABLE = 'channels'
DB_STATUS_TABLE = 'status'
DB_CATEGORIES_TABLE = 'categories'

sqlcmds = {
    'ct': [
        """
        CREATE TABLE IF NOT EXISTS channels (
            namespace VARCHAR(255) NOT NULL,
            instance  VARCHAR(255) NOT NULL,
            uid       VARCHAR(255) NOT NULL,
            number    VARCHAR(255) NOT NULL,
            display_number VARCHAR(255) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            group_tag     VARCHAR(255),
            updated   BOOLEAN NOT NULL,
            thumbnail VARCHAR(255),
            json TEXT NOT NULL,
            UNIQUE(namespace, instance, uid)
            )
        """,
        """
        CREATE TABLE IF NOT EXISTS status (
            namespace VARCHAR(255) NOT NULL,
            instance  VARCHAR(255),
            last_update timestamp,
            UNIQUE(namespace, instance)
            )
        """,
        """
        CREATE TABLE IF NOT EXISTS categories (
            namespace VARCHAR(255) NOT NULL,
            instance  VARCHAR(255),
            uid       VARCHAR(255) NOT NULL,
            category  VARCHAR(255) NOT NULL
            )
        """
    ],
    'channels_add':
        """
        INSERT INTO channels (
            namespace, instance, uid, number, display_number, display_name,
            thumbnail, updated, json
            ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ? )
        """,
    'channels_update':
        """
        UPDATE channels SET 
            number=?, thumbnail=?, updated=?, json=?
            WHERE namespace=? AND instance=? AND uid=?
        """,
    'status_add':
        """
        INSERT OR REPLACE INTO status (
            namespace, instance, last_update
            ) VALUES ( ?, ?, ? )
        """,
    'channels_updated_update':
        """
        UPDATE channels SET updated = False
        """,
    'channels_del':
        """
        DELETE FROM channels WHERE updated LIKE ?
        AND namespace=? AND instance=?
        """,

    'status_get':
        """
        SELECT last_update FROM status WHERE
            namespace=? AND instance=?
        """,
    'status_del':
        """
        DELETE FROM status WHERE
            namespace=? AND instance=?
        """,

    'channels_get':
        """
        SELECT * FROM channels WHERE namespace LIKE ?
        AND instance LIKE ? ORDER BY CAST(number as FLOAT)
        """,

    'channels_one_get':
        """
        SELECT * FROM channels WHERE uid=? AND namespace LIKE ?
        AND instance LIKE ?
        """
}


class DBChannels(DB):

    def __init__(self, _config):
        super().__init__(_config, _config['database']['channels_db'], sqlcmds)

    def save_channel_list(self, _namespace, _instance, _ch_dict):
        """
        Assume the list is complete and will remove any old channels not updated
        """
        self.update(DB_CHANNELS_TABLE + '_updated')
        for ch in _ch_dict:
            try:
                self.add(DB_CHANNELS_TABLE, (
                    _namespace,
                    _instance,
                    ch['id'],
                    ch['number'],
                    ch['number'],
                    ch['name'],
                    ch['thumbnail'],
                    True,
                    json.dumps(ch)))
            except sqlite3.IntegrityError:
                self.update(DB_CHANNELS_TABLE, (
                    ch['number'],
                    ch['thumbnail'],
                    True,
                    json.dumps(ch),
                    _namespace,
                    _instance,
                    ch['id']
                ))

            self.add(DB_STATUS_TABLE, (
                _namespace, _instance, datetime.datetime.now()))
        self.delete(DB_CHANNELS_TABLE, (False, _namespace, _instance,))


    def del_channels(self, _namespace, _instance):
        self.delete(DB_CHANNELS_TABLE, ('%', _namespace, _instance,))
    
    def del_status(self, _namespace, _instance):
        self.delete(DB_STATUS_TABLE, (_namespace, _instance,))

    def get_status(self, _namespace, _instance):
        result = self.get(DB_STATUS_TABLE,
            (_namespace, _instance))
        if result:
            return result[0][0]
        else:
            return None

    def get_channels(self, _namespace, _instance):
        if not _namespace:
            _namespace = '%'
        if not _instance:
            _instance = '%'

        rows_dict = {}
        rows = self.get_dict(DB_CHANNELS_TABLE, (_namespace, _instance,))
        for row in rows:
            ch = json.loads(row['json'])
            row['json'] = ch
            rows_dict[row['uid']] = row
        return rows_dict

    def get_channel(self, _uid, _namespace, _instance):
        if not _namespace:
            _namespace = '%'
        if not _instance:
            _instance = '%'

        rows = self.get_dict(DB_CHANNELS_TABLE + '_one', (_uid, _namespace, _instance,))
        for row in rows:
            ch = json.loads(row['json'])
            row['json'] = ch
            return row
        return None

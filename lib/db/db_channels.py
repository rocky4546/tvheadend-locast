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

import ast
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
            enabled   BOOLEAN NOT NULL,
            uid       VARCHAR(255) NOT NULL,
            number    VARCHAR(255) NOT NULL,
            display_number VARCHAR(255) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            group_tag     VARCHAR(255),
            updated   BOOLEAN NOT NULL,
            thumbnail VARCHAR(255),
            thumbnail_size VARCHAR(255),
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
            namespace, instance, enabled, uid, number, display_number, display_name,
            thumbnail, thumbnail_size, updated, json
            ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )
        """,
    'channels_update':
        """
        UPDATE channels SET 
            number=?, updated=?, json=?
            WHERE namespace=? AND instance=? AND uid=?
        """,
    'channels_editable_update':
        """
        UPDATE channels SET 
            enabled=?, display_number=?, display_name=?, group_tag=?, thumbnail=?, thumbnail_size=?
            WHERE namespace=? AND instance=? AND uid=?
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
    'channels_get':
        """
        SELECT * FROM channels WHERE namespace LIKE ?
        AND instance LIKE ? ORDER BY CAST(number as FLOAT), namespace, instance
        """,
    'channels_one_get':
        """
        SELECT * FROM channels WHERE uid=? AND namespace LIKE ?
        AND instance LIKE ?
        """,
    'channels_name_get':
        """
        SELECT DISTINCT namespace,instance FROM channels
        """,
    
    'status_add':
        """
        INSERT OR REPLACE INTO status (
            namespace, instance, last_update
            ) VALUES ( ?, ?, ? )
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
                    True,
                    ch['id'],
                    ch['number'],
                    ch['number'],
                    ch['name'],
                    ch['thumbnail'],
                    str(ch['thumbnail_size']),
                    True,
                    json.dumps(ch)))
            except sqlite3.IntegrityError:
                self.update(DB_CHANNELS_TABLE, (
                    ch['number'],
                    True,
                    json.dumps(ch),
                    _namespace,
                    _instance,
                    ch['id']
                ))

            self.add(DB_STATUS_TABLE, (
                _namespace, _instance, datetime.datetime.now()))
        self.delete(DB_CHANNELS_TABLE, (False, _namespace, _instance,))

    def update_channel(self, _ch):
        """
        Updates the editable fields for one channel
        """
        self.update(DB_CHANNELS_TABLE+'_editable', (
            _ch['enabled'],
            _ch['display_number'],
            _ch['display_name'],
            _ch['group_tag'],
            _ch['thumbnail'],
            str(_ch['thumbnail_size']),
            _ch['namespace'],
            _ch['instance'],
            _ch['uid']
        ))

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
            row['thumbnail_size'] = ast.literal_eval(row['thumbnail_size'])
            # handles the uid multiple times across instances
            if row['uid'] in rows_dict.keys():
                rows_dict[row['uid']].append(row)
            else:
                rows_dict[row['uid']] = []
                rows_dict[row['uid']].append(row)
        return rows_dict

    def get_channel_names(self):
        return self.get_dict(DB_CHANNELS_TABLE + '_name')

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

    def get_sorted_channels(self, _namespace, _instance, _first_sort_key=[None, True], _second_sort_key=[None, True]):
        """
        Using dynamic SQl to create a SELECT statement and send to the DB
        keys are [name_of_column, direction_asc=True]
        """
        where = ' WHERE namespace LIKE ? AND instance LIKE ? '
        orderby_front = ' ORDER BY '
        orderby_end = ' CAST(number as FLOAT), namespace, instance '
        orderby1 = self.get_channels_orderby(_first_sort_key[0], _first_sort_key[1])
        orderby2 = self.get_channels_orderby(_second_sort_key[0], _second_sort_key[1])
        sqlcmd = ''.join(['SELECT * FROM channels ', where, orderby_front, orderby1, orderby2, orderby_end])

        if not _namespace:
            _namespace = '%'
        if not _instance:
            _instance = '%'

        rows_dict = {}
        rows = self.get_dict(None, (_namespace, _instance,), sql=sqlcmd)
        for row in rows:
            ch = json.loads(row['json'])
            row['json'] = ch
            row['thumbnail_size'] = ast.literal_eval(row['thumbnail_size'])
        return rows
    
    def get_channels_orderby(self, _column, _ascending):
        str_types = ['namespace', 'instance', 'enabled', 'display_name', 'group_tag', 'thumbnail']
        float_types = ['uid', 'display_number']
        json_types = ['HD', 'callsign']
        if _ascending:
            dir = 'ASC'
        else:
            dir = 'DESC'
        if _column is None:
            return ''
        elif _column in str_types:
            return ''.join([_column, ' ', dir, ', '])
        elif _column in float_types:
            return ''.join(['CAST(', _column, ' as FLOAT) ', dir, ', '])
        elif _column in json_types:
            return ''.join(['JSON_EXTRACT(json, "$.', _column,  '") ', dir, ', '])    
        

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
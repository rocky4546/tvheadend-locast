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
import datetime

from lib.db.db import DB

DB_EPG_TABLE = 'epg'

sqlcmds = {
    'ct': [
        """
        CREATE TABLE IF NOT EXISTS epg (
            namespace VARCHAR(255) NOT NULL,
            instance  VARCHAR(255) NOT NULL,
            day       DATE NOT NULL,
            last_update TIMESTAMP,
            json      TEXT NOT NULL,
            UNIQUE(namespace, instance, day)
            )
        """
    ],

    'epg_add':
        """
        INSERT OR REPLACE INTO epg (
            namespace, instance, day, last_update, json
            ) VALUES ( ?, ?, ?, ?, ? )
        """,

    'epg_by_day_del':
        """
        DELETE FROM epg WHERE namespace=? AND instance=? AND day < DATE('now','-1 day')
        """,
    'epg_del':
        """
        DELETE FROM epg WHERE namespace=? AND instance=?
        """,

    'epg_last_update_get':
        """
        SELECT datetime(last_update, 'localtime') FROM epg WHERE
            namespace=? AND instance LIKE ? and day=?
        """,

    'epg_get':
        """
        SELECT * FROM epg WHERE
            namespace LIKE ? AND instance LIKE ? ORDER BY day
        """

}


class DBepg(DB):

    def __init__(self, _config):
        super().__init__(_config, _config['database']['epg_db'], sqlcmds)

    def save_program_list(self, _namespace, _instance, _day, _prog_list):
        self.add(DB_EPG_TABLE, (
            _namespace,
            _instance,
            _day,
            datetime.datetime.utcnow(),
            json.dumps(_prog_list)))

    def del_old_programs(self, _namespace, _instance):
        """
        Removes all records for this namespace/instance that are over 1 day old
        """
        self.delete(DB_EPG_TABLE +'_by_day', (_namespace, _instance,))

    def del_instance(self, _namespace, _instance):
        """
        Removes all records for this namespace/instance
        """
        self.delete(DB_EPG_TABLE, (_namespace, _instance,))


    def get_last_update(self, _namespace, _instance, _day):
        if not _instance:
            _instance = '%'
        result = self.get(DB_EPG_TABLE + '_last_update', (_namespace, _instance, _day,))
        if len(result) == 0:
            return None
        else:
            last_update = result[0][0]
            if last_update is not None:
                return datetime.datetime.fromisoformat(last_update)
            else:
                return None

    def init_get_query(self, _namespace, _instance):
        if not _namespace:
            _namespace = '%'
        if not _instance:
            _instance = '%'
        self.get_init(DB_EPG_TABLE, (_namespace, _instance,))

    def get_next_row(self):
        row = self.get_dict_next()
        namespace = None
        instance = None
        if row:
            namespace = row['namespace']
            instance = row['instance']
            json_data = json.loads(row['json'])
            row = json_data
        return row, namespace, instance

    def close_query(self):
        self.cur.close()
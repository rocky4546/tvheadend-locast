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

from lib.db.db import DB

sqlcmds = {
    'ct': [
        """
        CREATE TABLE IF NOT EXISTS area (
            name VARCHAR(255) NOT NULL,
            icon VARCHAR(255) NOT NULL,
            label VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            PRIMARY KEY(name)
            )
        """,
        """
        CREATE TABLE IF NOT EXISTS section (
            area VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            icon VARCHAR(255) NOT NULL,
            label VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            settings TEXT NOT NULL,
            FOREIGN KEY(area) REFERENCES area(name),
            UNIQUE(area, name)
            )
        """
    ],

    'dt': [
        """
        DROP TABLE IF EXISTS area
        """,
        """
        DROP TABLE IF EXISTS section
        """],

    'area_add':
        """
        INSERT OR REPLACE INTO area (
            name, icon, label, description
            ) VALUES ( ?, ?, ?, ? )
        """,
    'section_add':
        """
        INSERT OR REPLACE INTO section (
            area, name, icon, label, description, settings
            ) VALUES ( ?, ?, ?, ?, ?, ? )
        """,
    'area_get':
        """
        SELECT * from area WHERE name LIKE ? ORDER BY rowid
        """,
    'section_get':
        """
        SELECT * from section WHERE area = ? ORDER BY rowid
        """,
    'area_keys_get':
        """
        SELECT name from area ORDER BY rowid
        """
}


class DBConfigDefn(DB):

    def __init__(self, _config):
        super().__init__(_config, _config['database']['defn_db'], sqlcmds)

    def get_area_dict(self, _where=None):
        if not _where:
            _where = '%'
        return self.get_dict('area', (_where,))

    def get_area_json(self, _where=None):
        if not _where:
            _where = '%'
        return json.dumps(self.get_dict('area', (_where,)))

    def get_sections_dict(self, _where):
        rows_dict = {}
        rows = self.get_dict('section', (_where,))
        for row in rows:
            settings = json.loads(row['settings'])
            row['settings'] = settings
            rows_dict[row['name']] = row
        return rows_dict

    def get_areas(self):
        """ returns an array of the area names in id order
        """
        area_tuple = self.get('area_keys')
        areas = [area[0] for area in area_tuple]
        return areas

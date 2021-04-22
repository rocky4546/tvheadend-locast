'''
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
'''

import logging
import os
import pathlib
import sqlite3
import threading

DB_EXT = '.db'

# trailers used in sqlcmds.py
SQL_CREATE_TABLES = 'ct'
SQL_DROP_TABLES = 'dt'
SQL_ADD_ROW = '_add'
SQL_UPDATE = '_update'
SQL_GET = '_get'
SQL_DELETE = '_del'


class DB:
    conn = {}

    def __init__(self, _config, _db_name, _sqlcmds):
        self.logger = logging.getLogger(__name__)
        self.config = _config
        self.db_name = _db_name
        self.sqlcmds = _sqlcmds
        self.cur = None

        self.db_fullpath = pathlib.Path(self.config['paths']['db_dir']) \
            .joinpath(_db_name + DB_EXT)
        if not os.path.exists(self.db_fullpath):
            self.logger.debug('Creating new database: {} {}'.format(_db_name, self.db_fullpath))
            self.create_tables()
        self.check_connection()
        DB.conn[self.db_name][threading.get_ident()].commit()

    def sql_exec(self, _sqlcmd, _bindings=None):
        self.check_connection()
        if _bindings:
            return DB.conn[self.db_name][threading.get_ident()].execute(_sqlcmd, _bindings)
        else:
            return DB.conn[self.db_name][threading.get_ident()].execute(_sqlcmd)

    def add(self, _table, _values):
        sqlcmd = self.sqlcmds[''.join([_table, SQL_ADD_ROW])]
        cur = self.sql_exec(sqlcmd, _values)
        DB.conn[self.db_name][threading.get_ident()].commit()
        return cur.lastrowid

    def delete(self, _table, _values):
        sqlcmd = self.sqlcmds[''.join([_table, SQL_DELETE])]
        cur = self.sql_exec(sqlcmd, _values)
        DB.conn[self.db_name][threading.get_ident()].commit()
        return cur.lastrowid

    def update(self, _table, _values=None):
        sqlcmd = self.sqlcmds[''.join([_table, SQL_UPDATE])]
        cur = self.sql_exec(sqlcmd, _values)
        DB.conn[self.db_name][threading.get_ident()].commit()
        return cur.lastrowid

    def commit(self):
        DB.conn[self.db_name][threading.get_ident()].commit()
    

    def get(self, _table, _where=None):
        sqlcmd = self.sqlcmds[''.join([_table, SQL_GET])]
        cur = self.sql_exec(sqlcmd, _where)
        return cur.fetchall()

    def get_dict(self, _table, _where=None):
        sqlcmd = self.sqlcmds[''.join([_table, SQL_GET])]
        cur = self.sql_exec(sqlcmd, _where)
        records = cur.fetchall()
        rows = []
        for row in records:
            rows.append(dict(zip([c[0] for c in cur.description], row)))
        return rows

    def get_init(self, _table, _where=None):
        '''
            runs the query and returns the first row
            while maintaining the cursor. 
            Get_dict_next returns the next row
        '''
        sqlcmd = self.sqlcmds[''.join([_table, SQL_GET])]
        self.cur = self.sql_exec(sqlcmd, _where)

    def get_dict_next(self):
        row = self.cur.fetchone()
        row_dict = None
        if row:
            row_dict = dict(zip([c[0] for c in self.cur.description], row))
        return row_dict

    def reinitialize_tables(self):
        self.drop_tables()
        self.create_tables()

    def create_tables(self):
        for table in self.sqlcmds[''.join([SQL_CREATE_TABLES])]:
            self.sql_exec(table)

    def drop_tables(self):
        for table in self.sqlcmds[SQL_DROP_TABLES]:
            self.sql_exec(table)

    def close(self):
        for thread, conn in DB.conn[self.db_name].items():
            conn.close()
            self.logger.debug('{} database closed for thread:{}'.format(self.db_name, thread))

    def check_connection(self):
        if self.db_name not in DB.conn:
            DB.conn[self.db_name] = {}
        db_conn_dbname = DB.conn[self.db_name]
        
        if threading.get_ident() not in db_conn_dbname:
            db_conn_dbname[threading.get_ident()] = sqlite3.connect(
                self.db_fullpath, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        else:
            try:
                db_conn_dbname[threading.get_ident()].total_changes
            except sqlite3.ProgrammingError:
                self.logger.debug('Reopening {} database for thread:{}'.format(self.db_name, threading.get_ident()))
                db_conn_dbname[threading.get_ident()] = sqlite3.connect(
                    self.db_fullpath, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)



import logging
import os
import pathlib
import sqlite3
import threading

from lib.db.sqlcmds import sql

DB_EXT = '.db'
# trailers used in sqlcmds.py
SQL_CREATE_TABLE = '_ct'
SQL_DROP_TABLE = '_dt'
SQL_ADD_ROW = '_add'
SQL_GET = '_get'


class DB:
    conn = {}

    def __init__(self, _config, _db_name):
        self.logger = logging.getLogger(__name__)
        self.config = _config
        self.db_name = _db_name

        self.db_fullpath = pathlib.Path(self.config['paths']['db_dir']) \
            .joinpath(_db_name + DB_EXT)
        if not os.path.exists(self.db_fullpath):
            self.logger.info('Creating new database: {}'.format(_db_name))
        if len(DB.conn) == 0:
            new_db = True
        else:
            new_db = False
        self.check_connection()
        if new_db:
            self.create_tables()

    def sql_exec(self, _sqlcmd, _bindings=None):
        self.check_connection()
        if _bindings:
            return DB.conn[threading.get_ident()].execute(_sqlcmd, _bindings)
        else:
            return DB.conn[threading.get_ident()].execute(_sqlcmd)

    def add(self, _table, _values):
        sqlcmd = sql[''.join([self.db_name, '_', _table, SQL_ADD_ROW])]
        cur = self.sql_exec(sqlcmd, _values)
        DB.conn[threading.get_ident()].commit()
        return cur.lastrowid

    def get(self, _table, _where=None):
        sqlcmd = sql[''.join([self.db_name, '_', _table, SQL_GET])]
        if _where:
            cur = self.sql_exec(sqlcmd, _where)
        else:
            cur = self.sql_exec(sqlcmd)
        return cur.fetchall()

    def get_dict(self, _table, _where):
        sqlcmd = sql[''.join([self.db_name, '_', _table, SQL_GET])]
        cur = self.sql_exec(sqlcmd, _where)
        records = cur.fetchall()
        rows = []
        for row in records:
            rows.append(dict(zip([c[0] for c in cur.description], row)))
        return rows

    def create_tables(self):
        for table in sql[self.db_name + SQL_CREATE_TABLE]:
            self.sql_exec(table)

    def drop_tables(self):
        for table in sql[self.db_name + SQL_DROP_TABLE]:
            self.sql_exec(table)

    def close(self):
        for thread, conn in DB.conn.items():
            conn.close()
            self.logger.debug('Database closed for thread:{}'.format(thread))

    def check_connection(self):
        if threading.get_ident() not in DB.conn:
            DB.conn[threading.get_ident()] = sqlite3.connect(self.db_fullpath)
        else:
            try:
                DB.conn[threading.get_ident()].total_changes
            except sqlite3.ProgrammingError:
                self.logger.debug('Reopening database for thread:{}'.format(threading.get_ident()))
                DB.conn[threading.get_ident()] = sqlite3.connect(self.db_fullpath)

import json
import datetime
import sqlite3

from lib.db.db import DB


DB_EPG_TABLE = 'epg'


sqlcmds = {
    'ct': ["""
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

    
    'epg_add': """
    INSERT OR REPLACE INTO epg (
        namespace, instance, day, last_update, json
        ) VALUES ( ?, ?, ?, ?, ? )
    """,
    'epg_del': """
    DELETE FROM epg WHERE namespace=? AND instance=? AND day < DATE('now','-1 day')
    """,
    
    'epg_last_update_get':
    """
    SELECT last_update FROM epg WHERE
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
            datetime.datetime.now(),
            json.dumps(_prog_list)))
            
    def delete_old_programs(self, _namespace, _instance):
        '''
        Removes all records for this namespace/instance that are over 1 day old
        '''
        self.delete(DB_EPG_TABLE, (_namespace, _instance,))


    def get_last_update(self, _namespace, _instance, _day):
        if not _instance:
            _instance = '%'
        result = self.get(DB_EPG_TABLE+'_last_update', (_namespace, _instance, _day,))
        if len(result) == 0:
            return None
        else:
            return result[0][0]
    
    
    def init_get_query(self, _namespace, _instance):
        if not _namespace:
            _namespace = '%'
        if not _instance:
           _instance = '%'
        self.get_init(DB_EPG_TABLE, (_namespace, _instance,))

    
    def get_next_row(self):
        row = self.get_dict_next()
        if row:
            json_data = json.loads(row['json'])
            row = json_data
        return row
        
    
    

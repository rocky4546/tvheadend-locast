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

import datetime
import glob
import importlib
import inspect
import logging
import os
import pathlib
import shutil
import time
from lib.db.db_scheduler import DBScheduler
from lib.common.decorators import Backup
from lib.common.decorators import Restore
from lib.db.db_config_defn import DBConfigDefn

BACKUP_FOLDER_NAME = 'CarbernetBackup'

def scheduler_tasks(config):
    scheduler_db = DBScheduler(config)
    if scheduler_db.save_task(
            'Applications',
            'Backup',
            'internal',
            None,
            'lib.db.datamgmt.backups.backup_data',
            20,
            'thread',
            'Backs up cabernet including databases'
            ):
        scheduler_db.save_trigger(
            'Applications',
            'Backup',
            'weekly',
            dayofweek='Sunday',
            timeofday='02:00'
            )
    #Backup.log_backups()
    
def backup_data(_plugins):
    # get the location where the backups will be stored
    # also deal with the number of backup folder limit and clean up
    backups_to_retain = _plugins.config_obj.data['datamgmt']['backups-backupstoretain'] - 1
    backups_location = _plugins.config_obj.data['datamgmt']['backups-location']
    folderlist = sorted(glob.glob(os.path.join(backups_location, BACKUP_FOLDER_NAME+'*')))

    while len(folderlist) > backups_to_retain:
        try:
            shutil.rmtree(folderlist[0])
        except PermissionError as e:
            logging.warning(e)
            break
        folderlist = sorted(glob.glob(os.path.join(backups_location, BACKUP_FOLDER_NAME+'*')))
    new_backup_folder = BACKUP_FOLDER_NAME + datetime.datetime.now().strftime('_%Y%m%d_%H%M')
    new_backup_path = pathlib.Path(backups_location, new_backup_folder)

    for key in Backup.backup2func.keys():
        Backup.call_backup(key, _plugins.config_obj.data, backup_folder=new_backup_path)


def restore_data(_config, _folder, _key):
    """
    key is what the Back and Restore decorators use to lookup the function call_backup
    and is also tied to the config defn lookup under datamgmt
    """
    full_path = pathlib.Path(_config['datamgmt']['backups-location'], _folder)
    if os.path.isdir(full_path):
        return Restore.call_restore(_key, _config, backup_folder=full_path)
    else:
        return 'Folder does not exist: {}'.format(full_path)

def backup_list(_config_obj):
    """
    A list of dicts that contain what is backed up for use with restore.
    """
    db_confdefn = DBConfigDefn(_config_obj.data)
    dm_section = db_confdefn.get_one_section_dict('general', 'datamgmt')
    bkup_defn = {}
    for key in Restore.restore2func.keys():
        bkup_defn[key] = dm_section['datamgmt']['settings'][key]
    return bkup_defn
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
import json
import logging
import platform
import re
import shutil
import os

from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
import lib.db.datamgmt.backups as backups
from lib.db.db_channels import DBChannels
from lib.db.db_epg import DBepg
from lib.db.db_scheduler import DBScheduler


BACKUP_FOLDER_NAME = 'CarbernetBackup'


@getrequest.route('/pages/data_mgmt.html')
def get_data_mgmt_html(_webserver):
    plugin_list = _webserver.plugins.plugins.keys()
    data_mgmt_html = DataMgmtHTML(_webserver.plugins.config_obj, plugin_list)
    if 'delete' in _webserver.query_data:
        data_mgmt_html.del_backup(_webserver.query_data['delete'])
        html = data_mgmt_html.get()
    elif 'restore' in _webserver.query_data:
        html = data_mgmt_html.restore_form(_webserver.query_data['restore'])
    else:
        html = data_mgmt_html.get()
    _webserver.do_mime_response(200, 'text/html', html)


@postrequest.route('/pages/data_mgmt.html')
def post_data_mgmt_html(_webserver):
    plugin_list = _webserver.plugins.plugins.keys()
    data_mgmt_html = DataMgmtHTML(_webserver.plugins.config_obj, plugin_list)
    if 'folder' in _webserver.query_data:
        html = restore_from_backup(_webserver.plugins.config_obj, _webserver.query_data)
    elif 'action' in _webserver.query_data:
        action = _webserver.query_data['action'][0]
        if action == 'reset_channel':
            html = reset_channels(_webserver.plugins.config_obj.data, 
                _webserver.query_data['name'][0])
        elif action == 'reset_epg':
            html = reset_epg(_webserver.plugins.config_obj.data, 
                _webserver.query_data['name'][0])
        elif action == 'reset_scheduler':
            html = reset_sched(_webserver.plugins.config_obj.data,
                _webserver.query_data['name'][0])
        else:
            # database action request
            html = 'UNKNOWN action request: {}'.format(_webserver.query_data['action'][0])
    else:
        html = 'UNKNOWN REQUEST'
    _webserver.do_mime_response(200, 'text/html', html)


def reset_channels(_config, _name):
    db_channel = DBChannels(_config)
    db_channel.del_status(_name)
    if _name is None:
        return 'Channels updated and will refresh all data on next request'
    else:
        return 'Channels for plugin {} updated and will refresh all data on next request' \
            .format(_name)


def reset_epg(_config, _name):
    db_epg = DBepg(_config)
    db_epg.set_last_update(_name)
    if _name is None:
        return 'EPG updated and will refresh all days on next request'
    else:
        return 'EPG for plugin {} updated and will refresh all days on next request' \
            .format(_name)


def reset_sched(_config, _name):
    db_scheduler = DBScheduler(_config)
    tasks = db_scheduler.get_tasks_by_name(_name)
    html = ''
    for task in tasks:
        db_scheduler.del_task(task['area'], task['title'])
        html = ''.join([html, 
            '<b>', task['area'], ':', task['title'], 
            '</b> deleted from Scheduler<br>'
            ])
    return ''.join([html, 
        'Restart the app to re-populate the scheduler with defaults'])


def restore_from_backup(_config_obj, _query_data):
    bkup_defn = backups.backup_list(_config_obj)
    folder = _query_data['folder'][0]
    del _query_data['name']
    del _query_data['instance']
    del _query_data['folder']
    html = ''
    successful = True
    for restore_key, status in _query_data.items():
        if status[0] == '1':
            msg = backups.restore_data(_config_obj.data, folder, restore_key)
            if msg is None:
                html = ''.join([html, bkup_defn[restore_key]['label'], ' Restored<br>'])
            else:
                html = ''.join([html, msg, '<br>'])
                successful = False
    return html


class DataMgmtHTML:

    def __init__(self, _config_obj, _plugin_list):
        self.config_obj = _config_obj
        self.config = _config_obj.data
        self.plugin_names = _plugin_list
        self.logger = logging.getLogger(__name__)

    def get(self):
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="data management for Cabernet">',
            '<title>Data Management</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>',
            '<link rel="stylesheet" type="text/css" href="/modules/datamgmt/datamgmt.css">',
            '<script src="/modules/datamgmt/datamgmt.js"></script>'
            ])

    @property
    def title(self):
        return ''.join([
            '<body><div class="container">',
            '<h2>Data Management</h2>'
        ])

    @property
    def body(self):
        return ''.join(['<body>', self.title, self.db_updates, self.backups,
            '</body>'
            ])


    @property
    def db_updates(self):
        html = ''.join([
            '<section id="reset_status"></section>',
            '<form action="/pages/data_mgmt.html" method="post">',
            '<table class="dmTable" width=95%>',
            '<tr>',
            '<td class="dmIcon">',
            '<i class="md-icon">inventory_2</i></td>',
            '<td class="dmItem" >',
            '<div class="dmItemTitle">Reset Channel Data &nbsp; ',
            '<input type="hidden" name="action" value="reset_channel">',
            '<button type="submit">Reset</button></div>',
            '<div>Next channel request will force pull new data</div></td>',
        ])
        html_select = self.select_reset_channel
        html = ''.join([html, html_select,
            '<tr><td colspan=3><hr></td></tr></table></form>',
            '<form action="/pages/data_mgmt.html" method="post">',
            '<table class="dmTable" width=95%>',
            '<tr>',
            '<td class="dmIcon">',
            '<i class="md-icon">inventory_2</i></td>',
            '<td class="dmItem">',
            '<div class="dmItemTitle">Reset EPG Data &nbsp; ',
            '<input type="hidden" name="action" value="reset_epg">',
            '<button type="submit">Reset</button></div>',
            '<div>Next epg request will pull all days</div></td>',
        ])
        html_select = self.select_reset_epg
        html = ''.join([html, html_select,
            '<tr><td colspan=3><hr></td></tr></table></form>',
            '<form action="/pages/data_mgmt.html" method="post">',
            '<table class="dmTable" width=95%>',
            '<tr>',
            '<td class="dmIcon">',
            '<i class="md-icon">inventory_2</i></td>',
            '<td class="dmItem">',
            '<div class="dmItemTitle">Reset Scheduler Tasks &nbsp; ',
            '<input type="hidden" name="action" value="reset_scheduler">',
            '<button type="submit">Reset</button></div>',
            '<div>Scheduler will reload default tasks on next app restart</div></td>',
        ])
        html_select = self.select_reset_sched
        html = ''.join([html, html_select,
            '</select></td></tr>'
            '<tr><td colspan=3><hr></td></tr>',
            '</table></form><br>',
            ])
        return html

    
    @property
    def backups(self):
        html = ''.join([
            '<div id="dmbackup">',
            '<table class="dmTable" width=95%>',
            '<tr>',
            '<td colspan=3><div class="dmSection">',
            'Current Backups</div></td>'
            '</tr>',
        ])
        backups_location = self.config['datamgmt']['backups-location']
        folderlist = sorted(glob.glob(os.path.join(
            backups_location, BACKUP_FOLDER_NAME+'*')), reverse=True)
        for folder in folderlist:
            filename = os.path.basename(folder)
            datetime_str = self.get_backup_date(filename)
            if datetime_str is None:
                continue
            html = ''.join([html,
                '<tr>',
                '<td class="dmIcon">',
                '<a href="#" onclick=\'load_backup_url("/pages/data_mgmt.html?restore=',
                filename, '")\'>',
                '<i class="md-icon">folder</i></a></td>',
                '<td class="dmItem">',
                '<a href="#" onclick=\'load_backup_url("/pages/data_mgmt.html?restore=',
                filename, '")\'>',
                '<div class="dmItemTitle">', datetime_str, '</div>',
                '<div>', folder, '</div></td>',
                '<td class="dmIcon">',
                '<a href="#" onclick=\'load_dm_url("/pages/data_mgmt.html?delete=', 
                filename, '")\'>',
                '<i class="md-icon">delete_forever</i></a></td>',
                '</tr>'
            ])
        html = ''.join([html, 
            '</table>',
            '</div>'
            ])
        return html

    def del_backup(self, _folder):
        valid_regex = re.compile('^([a-zA-Z0-9_]+$)')
        if not valid_regex.match(_folder):
            self.logger.info('Invalid backup folder to delete: {}'.format(_folder))
            return
        backups_location = self.config['datamgmt']['backups-location']
        f_to_delete = os.path.join(backups_location, _folder)
        if os.path.isdir(f_to_delete):
            self.logger.info('Deleting backup folder {}'.format(_folder))
            shutil.rmtree(f_to_delete)
        else:
            self.logger.info('Backup folder not found to delete: {}'.format(_folder))

    def restore_form(self, _folder):
        datetime_str = self.get_backup_date(_folder)
        if datetime_str is None:
            return 'ERROR - UNKNOWN BACKUP FOLDER'

        html = ''.join([
            '<script src="/modules/datamgmt/restore_backup.js"></script>'
            '<form action="/pages/data_mgmt.html" method="post">',
            '<table class="dmTable" width=95%>',
            '<tr>',
            '<td class="dmIcon">',
            '<a href="#" onclick=\'load_dm_url("/pages/data_mgmt.html")\'>',
            '<div ><i class="md-icon">arrow_back</i></div></a></td>',
            '<td colspan=2 class="dmSection"><div >',
            'Backup from: ', datetime_str, '</div></td>'
            '</tr>',
            '<tr>',
            '<td></td>',
            '<td colspan=2><div>',
            'Select the items to restore</div></td>'
            '</tr>',
            '<tr><td colspan=3><section id="status"></section></td></tr>',
            '<tr><td colspan=3>',
            '<button class="dmButton" id="submit" STYLE="background-color: #E0E0E0; margin-top:1em" ',
            'type="submit"><b>Restore Now</b></button>',
            '</td></tr>'
            ])
        bkup_defn = backups.backup_list(self.config_obj)
        for key in bkup_defn.keys():
            html = ''.join([html, 
                '<tr>',
                '<td class="dmIcon">',
                '<input value="1" type="checkbox" name="', key, '" checked="checked">',
                '<input name="', key, '" value="0" type="hidden">',
                '</td>',
                '<td colspan=2>',
                bkup_defn[key]['label'],
                '</td>',
                '</tr>'
            ])
        html = ''.join([html, 
            '</table>',
            '<input type="hidden" name="folder" value="', _folder, '">',
            '</form>'
            ])
        return html

    def get_backup_date(self, _filename):
        try:
            datetime_obj = datetime.datetime.strptime(_filename, 
                BACKUP_FOLDER_NAME + '_%Y%m%d_%H%M')
        except ValueError as e:
            self.logger.info('Bad backup folder name {}: {}'.format(filename, e))
            return None
        opersystem = platform.system()
        if opersystem in ['Windows']:
            return datetime_obj.strftime('%m/%d/%Y, %#I:%M %p')
        else:
            return datetime_obj.strftime('%m/%d/%Y, %-I:%M %p')

    @property
    def select_reset_channel(self):
        db_channel = DBChannels(self.config)
        plugins_channel = db_channel.get_channel_names()
        html_option = ''.join([
            '<td nowrap>Plugin: <select id="name" name="name"</select>',
            '<option value="">ALL</option>'
            ])
        for name in plugins_channel:
            html_option = ''.join([html_option,
                '<option value="', name['namespace'], '">', name['namespace'], '</option>',
                ])
        return ''.join([html_option, '</select></td></tr>' ])

    @property
    def select_reset_epg(self):
        db_epg = DBepg(self.config)
        plugins_epg = db_epg.get_epg_names()
        html_option = ''.join([
            '<td nowrap>Plugin: <select id="name" name="name"</select>',
            '<option value="">ALL</option>',
            ])
        for name in plugins_epg:
            html_option = ''.join([html_option,
                '<option value="', name['namespace'], '">', name['namespace'], '</option>',
                ])
        return ''.join([html_option, '</select></td></tr>' ])

    @property
    def select_reset_sched(self):
        db_sched = DBScheduler(self.config)
        plugins_sched = db_sched.get_task_names()
        html_option = ''.join([
            '<td nowrap>Plugin: <select id="name" name="name"</select>',
            '<option value="">ALL</option>',
            ])
        for name in plugins_sched:
            html_option = ''.join([html_option,
                '<option value="', name['namespace'], '">', name['namespace'], '</option>',
                ])
        return ''.join([html_option, '</select></td></tr>' ])


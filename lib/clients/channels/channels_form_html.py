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

import io
import urllib

import lib.image_size.get_image_size as get_image_size
from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
import lib.common.utils as utils
import lib.clients.channels.channels as channels



@getrequest.route('/pages/channels_form.html')
def get_channels_form_html(_tuner, _namespace=None, _sort_col=None, _sort_dir=None):
    channels_form = ChannelsFormHTML(_tuner.channels_db, _tuner.config)
    if _namespace is None:
        name = _tuner.query_data['name']
    else:
        name = _namespace
    form = channels_form.get(name, _sort_col, _sort_dir)
    _tuner.do_mime_response(200, 'text/html', form)


@postrequest.route('/pages/channels_form.html')
def post_channels_html(_tuner):
    # Take each key and make a [section][key] to store the value
    channel_changes = {}
    namespace = _tuner.query_data['name'][0]
    sort_col = _tuner.query_data['sort_col'][0]
    sort_dir = _tuner.query_data['sort_dir'][0]
    print(sort_dir)
    del _tuner.query_data['name']
    del _tuner.query_data['instance']
    del _tuner.query_data['sort_dir']
    del _tuner.query_data['sort_col']
    
    if sort_col is None:
        results = channels.update_channels(_tuner.config, namespace, _tuner.query_data)
        _tuner.do_mime_response(200, 'text/html', results)
    else:
        get_channels_form_html(_tuner, namespace, sort_col, sort_dir)


class ChannelsFormHTML:

    def __init__(self, _channels_db, _config):
        self.db = _channels_db
        self.namespace = None
        self.config = _config
        self.active_tab_name = None
        self.num_of_channels = 0
        self.num_enabled = 0
        self.sort_column = None
        self.sort_direction = None

    def get(self, _namespace, _sort_col, _sort_dir):
        self.sort_column = _sort_col
        self.sort_direction = _sort_dir
        self.namespace = _namespace
        sort_data = self.get_db_sort_data(_sort_col, _sort_dir)
        self.ch_data = self.db.get_sorted_channels(self.namespace, None, sort_data[0], sort_data[1])
        return ''.join([self.header,self.body])

    def get_db_sort_data(self, _sort_col, _sort_dir):
        if _sort_dir == 'sortdesc':
            ascending = False
        elif _sort_dir == 'sortasc':
            ascending = True
        else:
            _sort_col = None
            ascending = True
        db_column2 = None
        if _sort_col == 'enabled':
            db_column1 = 'enabled'
            db_column2 = 'instance'
        elif _sort_col == 'instance':
            db_column1 = 'instance'
        elif _sort_col == 'num':
            db_column1 = 'display_number'
        elif _sort_col == 'name':
            db_column1 = 'display_name'
        elif _sort_col == 'group':
            db_column1 = 'group_tag'
        elif _sort_col == 'thumbnail':
            db_column1 = 'thumbnail'
        elif _sort_col == 'metadata':
            db_column1 = 'HD'
            db_column2 = 'callsign'
        else:
            db_column1 = None
        return [[db_column1, ascending], [db_column2, ascending]]





    @property
    def header(self):
        return ''.join([
            '<html><head>',
            '<script src="/modules/channels/channelsform.js"></script>',
            '<script src="/modules/table/table.js"></script>',
            '</head><body>'
            ])

    @property
    def form_header(self):
        header_dir = {
            'enabled':'sortnone',
            'instance':'sortnone',
            'num':'sortnone',
            'name':'sortnone',
            'group':'sortnone',
            'thumbnail':'sortnone',
            'metadata':'sortnone'
        }
        header_dir[self.sort_column] = self.sort_direction
        
        return ''.join([
            '<input type="hidden" name="name" value="', self.namespace, '" >',
            '<input type="hidden" name="sort_col" >',
            '<input type="hidden" name="sort_dir" >',
            '<table><tr><td>Total Unique Channels = ', str(self.num_of_channels), '</td></tr>',
            '<tr><td>Total Enabled Unique Channels = ', str(self.num_enabled), '</td>'
            '<td style="min-width:18ch; text-align: center">',
            '<button STYLE="background-color: #E0E0E0;" ',
            'type="submit"><b>Save changes</b></button>',
            '</td></tr></table>',
            '<table class="sortable" ><thead><tr>',
            '<th style="min-width: 7ch;" class="header">'
            '<input id="enabled" type=checkbox>',
            '<label title="enabled=green, disabled=red, disabled dup=violet, duplicate=yellow indicator">',
            '<img class="sortit ', header_dir['enabled'], '">',
            '<img class="filterit"><span class=vertline><img></span></label></th>',
            '<th style="min-width: 11ch;" class="header"><label title="Table is for a plugin. Each row has an instance for a channel">',
            'instance',
            '<img class="sortit ', header_dir['instance'], '">',
            '<img class="filterit"><span class=vertline><img></span></label></th>',
            '<th style="min-width: 8ch;" class="header"><label title="Channel number.  DVR may require this to be a number">',
            'num',
            '<img class="sortit ', header_dir['num'], '">',
            '<img class="filterit"><span class=vertline><img></span></label></th>',
            '<th style="min-width: 10ch;" class="header"><label title="Channel display name">',
            'name',
            '<img class="sortit ', header_dir['name'], '">',
            '<img class="filterit"><span class=vertline><img></span></label></th>',
            '<th style="min-width: 10ch;" class="header"><label title="Group or tag name. Expects only one value">',
            'group',
            '<img class="sortit ', header_dir['group'], '">',
            '<span class="filter"><img class="filterit"></span><span class=vertline><img></span></label></th>',
            '<th class="header"><label title="Use http:// https:// or (Linux) file:/// (Windows) file:///C:/ Be careful when using spaces in the path">',
            'thumbnail',
            '<img class="sortit ', header_dir['thumbnail'], '">',
            '<span class="filter"><img class="filterit"></span><span class=vertline><img></span></label></th>',
            '<th class="header"><label title="Extra data used in filtering">',
            'metadata',
            '<img class="sortit ', header_dir['metadata'], '">',
            '<span class="filter"><img class="filterit"></span><span class=vertline><img></span></label></th>',
            '</tr></thead>'
            ])

    @property
    def form(self):
        t = self.table
        forms_html = ''.join(['<form id="channelform" ',
            'action="/pages/channels_form.html" method="post">',
            self.form_header, t, '</form>'])
        return forms_html

    @property
    def table(self):
        table_html = '<tbody>'
        sids_processed = {}
        for sid_data in self.ch_data:
            sid = sid_data['uid']
            instance = sid_data['instance']
            if sid_data['enabled']:
                enabled = 'checked'
                enabled_status = "enabled"
            else:
                enabled = ''
                enabled_status = "disabled"
            if sid in sids_processed.keys():
                if sid_data['enabled']:
                    enabled_status = "duplicate"
                else:
                    enabled_status = "duplicate_disabled"
            else:
                sids_processed[sid] = sid_data['enabled']


            if sid_data['json']['HD']:
                quality = 'HD'
            else:
                quality = 'SD'
            max_image_size = self.lookup_config_size()
            if sid_data['thumbnail_size'] is not None:
                image_size = sid_data['thumbnail_size']
                thumbnail_url = utils.process_image_url(self.config, sid_data['thumbnail'])
                if max_image_size is None:
                    display_image = ''.join(['<img border=1 src="', thumbnail_url, '">'])
                elif max_image_size == 0:
                    display_image = ''
                else:
                    if image_size[0] < max_image_size:
                        img_width = str(image_size[0])
                    else:
                        img_width = str(max_image_size)
                    display_image = ''.join(['<img width="', img_width, '" border=1 src="', thumbnail_url, '">'])
            else:
                display_image = ''
                image_size = 'UNK'
                img_width = 0
                
            if sid_data['json']['thumbnail_size'] is not None:
                original_size = sid_data['json']['thumbnail_size']
            else:
                original_size = 'UNK'
            row = ''.join([
                '<tr><td style="text-align: center" class="', enabled_status, '">',
                '<input value="1" type=checkbox name="',
                self.get_input_name(sid, instance, 'enabled'),
                '" ', enabled, '>',
                '<input value="0" type="hidden" name="',
                self.get_input_name(sid, instance, 'enabled'),
                '">',
                '</td>',
                '<td style="text-align: center">', instance, '</td>',
                '<td style="text-align: center">', 
                self.get_input_text(sid_data, sid, instance, 'display_number'), '</td>',
                '<td style="text-align: center">', 
                self.get_input_text(sid_data, sid, instance, 'display_name'), '</td>',
                '<td style="text-align: center">', 
                self.get_input_text(sid_data, sid, instance, 'group_tag'), '</td>',
                '<td><table width="100%"><tr><td style="border: none; background: none;">', 
                self.get_input_text(sid_data, sid, instance, 'thumbnail'),
                '</td></tr><tr><td style="border: none; background: none;">',
                display_image,
                '</td></tr><tr><td style="border: none; background: none;">',
                'size=', str(image_size), '   original_size=', str(original_size),
                '</td></tr></table></td>',
                '<td style="text-align: center">', quality, ' ',
                sid_data['json']['callsign'], ' ', sid, '</td>',
                '</tr>'
                ])
            table_html += row
        self.num_of_channels = len(sids_processed.keys())
        self.num_enabled = sum(x == True for x in sids_processed.values())
        return ''.join([table_html, '</tbody></table>'])

    def get_input_text(self, _sid_data, _sid, _instance, _title):
        if _sid_data[_title] is not None:
            return ''.join(['<input type="text" name="',
                self.get_input_name(_sid, _instance, _title),
                '" value="', _sid_data[_title], 
                '" size="', str(len(_sid_data[_title])), '">'])
        else:
            return ''.join(['<input type="text" name="',
                self.get_input_name(_sid, _instance, _title),
                '" size="5">'])


    def get_input_name(self, _sid, _instance, _title):
        return  ''.join([_sid, '-', _instance, '-', _title])

    @property
    def body(self):
        return ''.join([
            '<section id="status"></section>',
            self.form,
            '<footer><p>Clearing any field and saving will revert to the default value. Help is provided on the column titles.',
            ' First column displays the status of the channel: either enabled, disabled or duplicate (enabled or disabled).',
            ' The thumbnail field must have an entry; not using the thumbnail is a configuration parameter under Settings - Clients - EPG.',
            ' The size of the thumbnail presented in the table is set using the configuration parameter under Settings - Internal - Channels.</p>',
            '</footer></body>'])

    def lookup_config_size(self):
        size_text = self.config['channels']['thumbnail_size']
        if size_text == 'None':
            return 0
        elif size_text == 'Tiny(16)':
            return 16
        elif size_text == 'Small(48)':
            return 48
        elif size_text == 'Medium(128)':
            return 128
        elif size_text == 'Large(180)':
            return 180
        elif size_text == 'X-Large(270)':
            return 270
        elif size_text == 'Full-Size':
            return None
        else:
            self.logger.warning('UNKNOWN [channels][thumbnail_size] = {}'.format(size_text))
            return None

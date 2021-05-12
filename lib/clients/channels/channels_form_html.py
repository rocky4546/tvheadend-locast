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

import urllib
import io


import json

from lib.web.pages.templates import web_templates
from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
import lib.clients.channels.channels as channels
import lib.image_size.get_image_size as get_image_size


@getrequest.route('/pages/channels_form.html')
def get_channels_form_html(_tuner):
    channels_form = ChannelsFormHTML(_tuner.channels_db, _tuner.config)
    form = channels_form.get(_tuner.query_data['name'])
    _tuner.do_mime_response(200, 'text/html', form)


@postrequest.route('/pages/channels_form.html')
def post_channels_html(_tuner):
    # Take each key and make a [section][key] to store the value
    config_changes = {}
    area = _tuner.query_data['area'][0]
    del _tuner.query_data['area']
    namespace = _tuner.query_data['name']
    del _tuner.query_data['name']
    instance = _tuner.query_data['instance']
    del _tuner.query_data['instance']
    for key in _tuner.query_data:
        key_pair = key.split('-', 1)
        if key_pair[0] not in config_changes:
            config_changes[key_pair[0]] = {}
        config_changes[key_pair[0]][key_pair[1]] = _tuner.query_data[key]
    results = _tuner.plugins.config_obj.update_config(area, config_changes)
    _tuner.do_mime_response(200, 'text/html', results)


class ChannelsFormHTML:

    def __init__(self, _channels_db, _config):
        self.db = _channels_db
        self.namespace = None
        self.config = _config
        self.active_tab_name = None

    def get(self, _namespace):
        self.namespace = _namespace
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<form id="channelform" ',
            'action="/pages/channels_form.html" method="post">',
            '<table><tr><td>Total Channels = 42</td></tr>',
            '<tr><td>Total Enabled Channels = 25</td></tr></table>',
            '<table class="sortable" ><thead><tr>',
            '<th class="header"></th>',
            '<th class="header">instance<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '<th class="header">num<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '<th class="header">name<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '<th class="header">group<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '<th class="header">thumbnail<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '<th class="header">metadata<img class="sortit"><span class="filter"><img class="filterit"></span><span class=vertline><img></span></th>',
            '</tr></thead>'
            ])

    @property
    def form(self):
        #forms_html = '</form>'
        forms_html = self.table + '</form>'
        return forms_html

    @property
    def table(self):
        ch_data = self.db.get_channels(self.namespace, None)
        section_html = '<tbody>'
        for sid, sid_data in ch_data.items():
            if sid_data['enabled']:
                enabled = 'checked'
            else:
                enabled = ''
            if sid_data['group_tag'] is None:
                group_cell = '<td></td>'
            else:
                group_cell = '<td>', sid_data['group_tag'], '</td>',
            if sid_data['json']['HD']:
                quality = 'HD'
            else:
                quality = 'SD'
            max_image_size = self.lookup_config_size()
            if sid_data['thumbnail_size'] is not None:
                image_size = sid_data['thumbnail_size']
                if max_image_size is not None:
                    if image_size[0] < max_image_size:
                        img_width = str(image_size[0])
                    else:
                        img_width = str(max_image_size)
                    display_image = ''.join(['<img width="', img_width, '" border=1 src="', sid_data['thumbnail'], '">'])
                else:
                    display_image = ''.join(['<img border=1 src="', sid_data['thumbnail'], '">'])
            else:
                display_image = ''
                image_size = 'UNK'
                img_width = 0
                
            print(display_image)
            if sid_data['json']['thumbnail_size'] is not None:
                original_size = sid_data['json']['thumbnail_size']
            else:
                original_size = 'UNK'
                
            row = ''.join([
                '<tr><td style="text-align: center"><input type=hidden value="', sid, '">',
                '<input type=checkbox ', enabled, '></td>',
                '<td style="text-align: center">', sid_data['instance'], '</td>',
                '<td style="text-align: center">', sid_data['display_number'], '</td>',
                '<td style="text-align: center">', sid_data['display_name'], '</td>',
                group_cell,
                '<td style="display: grid">', sid_data['thumbnail'],
                display_image,
                'size=', str(image_size), '   original_size=', str(original_size),
                '</td>',
                '<td style="text-align: center">', quality, ' ',
                sid_data['json']['callsign'], '</td>',
                '</tr>'
                ])
            section_html += row
        return ''.join([section_html, '</tbody></table>'
            '<button STYLE="background-color: #E0E0E0; margin-top:1em" ',
            'type="submit"><b>Save changes</b></button>'
            ])

    @property
    def body(self):
        return ''.join([
            self.form,
            '<section id="status"></section>',
            '<footer><p>Not all configuration parameters are listed 2.  ',
            'Edit the config file directly to change any parameters.</p>',
            '</footer>'])

    def lookup_config_size(self):
        size_text = self.config['channels']['thumbnail_size']
        if size_text == 'Tiny(16)':
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

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

from lib.web.pages.templates import web_templates
from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
import lib.clients.channels.channels as channels


@getrequest.route('/pages/channels_form.html')
def get_channels_form_html(_tuner):
    channels_form = ChannelsFormHTML(_tuner.channels_db)
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

    def __init__(self, _channels_db):
        self.db = _channels_db
        self.namespace = None
        self.config = None
        self.active_tab_name = None

    def get(self, _namespace):
        self.namespace = _namespace
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<table border=3><tr><td>cell1</td><td>cell2</td>',
            '<td>cell3</td><td>cell4</td>',
            '<td>cell5</td><td>', self.namespace, '</td>',
            '</tr></table>'])

    @property
    def forms(self):
        forms_html = '<div id="formcontent">WELL IS NOT THIS A SURPRISE!!!</div>'
        #for section in self.config_defn['sections'].keys():
        #    area_html = ''.join([area_html, self.get_form(section)])
        return forms_html

    def get_form(self, _section):
        input_html = "*** UNKNOWN INPUT TYPE ***"
        section_data = self.config_defn['sections'][_section]
        form_html = ''.join([
            '<form id="form', section_data['name'], '" class="sectionForm" ',
            'action="/pages/channels.html" method="post">',
            section_data['description'],
            '<table>'
        ])
        section_html = '<tbody>'
        subsection = None
        is_section_new = False
        for setting, setting_data in section_data['settings'].items():
            if setting_data['level'] == 4:
                continue
            title = ''
            readonly = ''

            new_section = None
            if '-' in setting:
                new_section = setting.split('-', 1)[0]
            if new_section != subsection and new_section is not None:
                is_section_new = True
                subsection = new_section
                
            background_color = '#F0F0F0'
            if setting_data['help'] is not None:
                title = ''.join([' title="', setting_data['help'], '"'])

            if 'writable' in setting_data and not setting_data['writable']:
                readonly = ' readonly'
                background_color = '#C0C0C0'

            if setting_data['type'] == 'string' \
                    or setting_data['type'] == 'path':
                input_html = ''.join([
                    '<input STYLE="background-color: ',
                    background_color, ';"  type="text"', readonly,
                    ' name="', section_data['name'], '-', setting, '">'])

            if setting_data['type'] == 'password':
                input_html = ''.join([
                    '<input STYLE="background-color: ',
                    background_color, ';"  type="password"', readonly,
                    ' name="', section_data['name'], '-', setting, '">'])

            elif setting_data['type'] == 'integer' \
                    or setting_data['type'] == 'float':
                input_html = ''.join([
                    '<input STYLE="background-color: ',
                    background_color, ';" type="number"', readonly,
                    ' name="', section_data['name'], '-', setting, '">'])

            elif setting_data['type'] == 'boolean':
                if 'writable' in setting_data and not setting_data['writable']:
                    readonly = ' disabled'

                input_html = ''.join([
                    '<input value="1" STYLE="background-color: ',
                    background_color, ';" type="checkbox"', readonly,
                    ' name="', section_data['name'], '-', setting, '">'
                                                                   '<input value="0" id="', setting,
                    'hidden" type="hidden"',
                    ' name="', section_data['name'], '-', setting, '">'
                ])

            elif setting_data['type'] == 'list':
                dlsetting = ''
                if section_data['name'] == 'display' and setting == 'display_level':
                    dlsetting = ' class="dlsetting" '

                option_html = ''.join(['<option value="">default</option>'])
                for value in setting_data['values']:
                    option_html += ''.join([
                        '<option value="', value, '">', value, '</option>'])
                input_html = ''.join([
                    '<select STYLE="background-color: ',
                    background_color, ';"', readonly,
                    dlsetting,
                    'name="', section_data['name'], '-', setting, '">',
                    option_html, '</select>'])

            if is_section_new:
                is_section_new = False
                section_html = ''.join([section_html,
                '<tr class="hlevel"><td><hr><h3>', subsection.upper(), '</h3></td></tr>'])

            section_html = ''.join([section_html,
                '<tr class="dlevel', str(setting_data['level']),
                '"><td><label ', title,
                '>', setting_data['label'], '</label></td><td>', input_html,
                '</td></tr>'])
        return ''.join([form_html, section_html, '</tbody></table>'
                                                 '<button STYLE="background-color: #E0E0E0; margin-top:1em" ',
            'type="submit"><b>Save changes</b></button>',
            '<input type=hidden name="area" value="', self.area, '"></form>'])

    @property
    def body(self):
        return ''.join([
            self.forms,
            '<section id="status"></section>',
            '<footer><p>Not all configuration parameters are listed.  ',
            'Edit the config file directly to change any parameters.</p>',
            '</footer></div></body></html>'])


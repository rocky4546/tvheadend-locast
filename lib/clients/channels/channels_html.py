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


@getrequest.route('/pages/channels.html')
def get_channels_html(_tuner):
    channels_html = ChannelsHTML(_tuner.channels_db)
    html = channels_html.get()
    _tuner.do_mime_response(200, 'text/html', html)


class ChannelsHTML:

    def __init__(self, _channels_db):
        self.db = _channels_db
        self.config = None
        self.active_tab_name = None

    def get(self):
        self.tab_names = self.get_channels_tabs()
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="channel editor for Cabernet">',
            '<title>Channel Editor</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>',
            '<link rel="stylesheet" type="text/css" href="/modules/tabs/tabs.css">',
            '<link rel="stylesheet" type="text/css" href="/modules/table/table.css">',
            '<script src="/modules/tabs/tabs.js"></script>',
            '<script src="/modules/pages/channels.js"></script></head>',
            '<script>load_form_url("/pages/channels_form.html?name=',
            list(self.tab_names.keys())[0], '")</script>' ])

    @property
    def title(self):
        return ''.join([
            '<body><div class="container">',
            '<h2>Channel Editor</h2>'
        ])

    @property
    def tabs(self):
        active_tab = ' activeTab'
        tabs_html = ''.join(['<ul class="tabs">'])
        for name in self.tab_names.keys():
            tabs_html = ''.join([tabs_html,
                '<li><a id="tab', name, '" class="form',
                name, ' configTab', active_tab, 
                '" href="#" onclick=\'load_form_url("/pages/channels_form.html?name=',
                name, '")\'>',
                '<i class="md-icon tabIcon">view_list',
                '</i>',
                name, '</a></li>'
            ])
            active_tab = ''
            self.active_tab_name = name
        tabs_html = ''.join([tabs_html, '</ul>'])
        return tabs_html

    @property
    def body(self):
        return ''.join([
            self.title,
            self.tabs,
            '<div id="tablecontent">EMPTY DIV AREA FOR TABLES</div>'
            ])

    def get_channels_tabs(self):
        ch_list = self.db.get_channel_names()
        return_list = {}
        for ch_names in ch_list:
            return_list[ch_names['namespace']] = None
        return return_list


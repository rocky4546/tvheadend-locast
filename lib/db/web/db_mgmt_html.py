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

import json

from lib.common.decorators import getrequest


@getrequest.route('/pages/db_mgmt.html')
def get_db_mgmt_html(_webserver):
    db_mgmt_html = DBMgmtHTML(_webserver.config)
    html = db_mgmt_html.get()
    _webserver.do_mime_response(200, 'text/html', html)


class DBMgmtHTML:

    def __init__(self, _config):
        self.config = _config

    def get(self):
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="database management for Cabernet">',
            '<title>Database Management</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>'])

    @property
    def title(self):
        return ''.join([
            '<body><div class="container">',
            '<h2>Database Management</h2>'
        ])

    @property
    def body(self):
        return ''.join([
            self.title,
            '<div id="tablecontent"><ul>',
            '<li>Reset Channel Data</li>',
            '<li>Reset EPG Data</li>',
            '<li>Backup Databases</li>',
            '<li>Restore Databases from backup</li>',
            '</ul></div>'
            ])

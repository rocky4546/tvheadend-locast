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

from lib.common.decorators import getrequest


@getrequest.route('/pages/index.js')
def pages_index_js(_tuner):
    indexjs = IndexJS()
    _tuner.do_mime_response(200, 'text/javascript', indexjs.get(_tuner.config))


class IndexJS:

    @staticmethod
    def get(_config):
        js = ''.join([
            '$(document).ready(function(){',
                '$(\'head\').append(\'<link rel="stylesheet"',
                    ' href="/modules/themes/',
                    _config['display']['theme'],
                    '/theme.css"',
                    ' type="text/css" />',
                    '<script type="text/javascript"',
                    ' src="/modules/themes/',
                    _config['display']['theme'],
                    '/theme.js"></script>',
                    '\')});',
            '$(document).ready(setTimeout(function(){',
                'logo = getComputedStyle(document.documentElement)',
                    '.getPropertyValue("--logo-url");',
                    '$("#content").html("<img class=\'splash\' src=\'"+logo+"\'>")',
                    '}, 1000));'
            'function load_url(url) {',
                '$("#content").load(url);}'
        ])
        return js


class IndexJS():

    def get(self, config):
        js = ''.join([
            '$(document).ready(function(){',
                '$(\'head\').append(\'<link rel="stylesheet"',
                    ' href="/web/modules/themes/',
                    config['display']['theme'],
                    '/theme.css"',
                    ' type="text/css" />',
                    '<script type="text/javascript"',
                    ' src="/web/modules/themes/',
                    config['display']['theme'],
                    '/theme.js"></script>',
                    '\')});'
        ])
        return js
        
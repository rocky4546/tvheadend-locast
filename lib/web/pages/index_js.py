        
class IndexJS:

    def get(self, _config):
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


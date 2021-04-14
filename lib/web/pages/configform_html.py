

class ConfigFormHTML:

    def __init__(self):
        self.area = None
        self.config_defn = None

    def get(self, _config_defn, _area):
        self.area = _area
        self.config_defn = _config_defn
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="config editor for tvheadend-locast">',
            '<title>Settings Editor</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<link rel="stylesheet" type="text/css" href="/modules/pages/configform.css">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>',
            '<link rel="stylesheet" type="text/css" href="/modules/tabs/tabs.css">',
            '<script src="/modules/tabs/tabs.js"></script>',
            '<script src="/modules/pages/configform.js"></script></head>'])

    @property
    def title(self):
        return ''.join([
            '<body><div class="container">',
            '<h2>Settings Editor - ',
            self.config_defn['label'],
            '</h2><div>',
            self.config_defn['description'],
            '<ul style="list-style: none; float:right; ',
            'margin: 0px; padding-left:0px;">',
            '<li><form>',
            '<select style="background-color: #F0F0F0; float:right;"',
            ' class="dlevelsetting"  name="display-display_level">',
            '<option value="">default</option>',
            '<option value="0-Basic">0-Basic</option>',
            '<option value="1-Standard">1-Standard</option>',
            '<option value="2-Expert">2-Expert</option>',
            '<option value="3-Advanced">3-Advanced</option>',
            '</select></form></li></ul></div>'
        ])

    @property
    def tabs(self):
        active_tab = ' activeTab'
        area_html = ''.join(['<ul class="tabs">'])
        for section, section_data in self.config_defn['sections'].items():
            area_html = ''.join([area_html,
                '<li><a id="tab', section_data['name'], '" class="form',
                section_data['name'], ' configTab', active_tab, '" href="#">',
                '<i class="md-icon tabIcon">',
                section_data['icon'], '</i>',
                section_data['label'], '</a></li>'
            ])
            active_tab = ''
        area_html = ''.join([area_html, '</ul>'])
        return area_html

    @property
    def forms(self):
        area_html = ''
        for section in self.config_defn['sections'].keys():
            area_html = ''.join([area_html, self.get_form(section)])
        return area_html

    def get_form(self, _section):
        input_html = "*** UNKNOWN INPUT TYPE ***"
        section_data = self.config_defn['sections'][_section]
        form_html = ''.join([
            '<form id="form', section_data['name'], '" class="sectionForm" ',
            'action="/pages/configform.html" method="post">',
            section_data['description'],
            '<table>'
        ])
        section_html = '<tbody>'
        for setting, setting_data in section_data['settings'].items():
            if setting_data['level'] == 4:
                continue
            title = ''
            readonly = ''

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
                dlevelsetting = ''
                if section_data['name'] == 'display' and setting == 'display_level':
                    dlevelsetting = ' class="dlevelsetting" '

                option_html = ''.join(['<option value="">default</option>'])
                for value in setting_data['values']:
                    option_html += ''.join([
                        '<option value="', value, '">', value, '</option>'])
                input_html = ''.join([
                    '<select STYLE="background-color: ',
                    background_color, ';"', readonly,
                    dlevelsetting,
                    'name="', section_data['name'], '-', setting, '">',
                    option_html, '</select>'])

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
            self.title,
            self.tabs,
            self.forms,
            '<section id="status"></section>',
            '<footer><p>Not all configuration parameters are listed.  ',
            'Edit the config file directly to change any parameters.</p>',
            '</footer></div></body></html>'])
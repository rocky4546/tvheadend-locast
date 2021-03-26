



class ConfigFormHTML():

    def get(self, config_defn):
        return ''.join([self.get_header(), self.get_body(config_defn)])

    def get_header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="config editor for tvheadend-locast">',
            '<title>TVHeadend-Locast Config Editor</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<link rel="stylesheet" type="text/css" href="/html/pages/configform.css">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>',
            '<script src="/html/pages/configform.js"></script></head>'])




    def get_form(self, config_defn):
        for area, area_data in config_defn.items():
            area_html = ''.join([
                '<form id="ConfigForm" ',
                'action="/pages/configform.html" method="post"><table>'])
            for section, section_data in area_data['sections'].items():
                section_html = ''.join([
                    '<tr class="dsection"><th>', section_data['label'], 
                    '</th></tr><tbody>'])
                for setting, setting_data in section_data['settings'].items():
                    if setting_data['level'] == 4:
                        continue
                    title = ''
                    readonly = ''
                    background_color = '#E0E0E0'
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
                            ' name="', section, '-', setting, '">'])

                    if setting_data['type'] == 'password':
                        input_html = ''.join([
                            '<input STYLE="background-color: ', 
                            background_color, ';"  type="password"', readonly,  
                            ' name="', section, '-', setting, '">'])

                    elif setting_data['type'] == 'integer' \
                            or setting_data['type'] == 'float':
                        input_html = ''.join([
                            '<input STYLE="background-color: ', 
                            background_color, ';" type="number"', readonly,
                            ' name="', section, '-', setting, '">'])

                    elif setting_data['type'] == 'boolean':
                        if 'writable' in setting_data and not setting_data['writable']:
                            readonly = ' disabled'
                    
                        input_html = ''.join([
                            '<input value="1" STYLE="background-color: ', 
                            background_color, ';" type="checkbox"', readonly,
                            ' name="', section, '-', setting, '">'
                            ])

                    elif setting_data['type'] == 'list':
                        option_html = ''.join(['<option value="">default</option>'])
                        for value in setting_data['values']:
                            option_html += ''.join([
                                '<option value="', value, '">', value, '</option>'])
                        input_html = ''.join([
                            '<select STYLE="background-color: ', 
                            background_color, ';"', readonly,
                            ' name="', section, '-', setting, '">',
                            option_html, '</select>'])
                    
                    section_html = ''.join([section_html, 
                        '<tr class="dlevel', str(setting_data['level']),
                        '"><td><label', title, 
                        '>', setting_data['label'], '</label></td><td>', input_html, 
                        '</td></tr>'])
                area_html = ''.join([area_html, section_html, '</tbody>'])
        return ''.join([area_html, '</table>',
            '<button STYLE="background-color: #E0E0E0;" ', 
            'id="save" type="submit"><b>Save changes</b></button></form>'])



    def get_body(self, config_defn):
        return ''.join([
            '<body><div class="container"><header>',
            '<h1>Config Editor: TVHeadend-Locast</h1></header>',
            self.get_form(config_defn),
            '<section id="status"></section>',
            '<footer><p>Not all configuration parameters are listed.  ',
            'Edit the config file directly to change any parameters.</p>',
            '</footer></div></body></html>'])










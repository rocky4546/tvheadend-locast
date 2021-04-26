# pylama:ignore=E722
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

import logging
import xml.dom.minidom as minidom
from xml.etree import ElementTree

import lib.tvheadend.epg_category as epg_category
from lib.db.db_epg import DBepg
from lib.db.db_channels import DBChannels


class EPG:

    def __init__(self, _plugins, _namespace, _instance):
        self.logger = logging.getLogger(__name__)
        self.config = _plugins.config_obj.data
        self.epg_db = DBepg(self.config)
        self.channels_db = DBChannels(self.config)
        self.plugins = _plugins
        self.namespace = _namespace
        self.instance = _instance

    def get_epg_xml(self):
        self.plugins.refresh_epg(self.namespace, self.instance)
        xml_out = EPG.gen_header_xml()
        channel_list = self.channels_db.get_channels(self.namespace, self.instance)
        self.gen_channel_xml(xml_out, channel_list)
        self.epg_db.init_get_query(self.namespace, self.instance)
        day_data = self.epg_db.get_next_row()
        while day_data:
            self.gen_program_xml(xml_out, day_data)
            day_data = self.epg_db.get_next_row()
        epg_dom = minidom.parseString(ElementTree.tostring(xml_out, encoding='UTF-8', method='xml'))
        return epg_dom.toprettyxml()

    def gen_channel_xml(self, _et_root, _channel_list):
        for sid, ch_data in _channel_list.items():
            prefix = self.config[ch_data['namespace'].lower()]['epg-prefix']
            suffix = self.config[ch_data['namespace'].lower()]['epg-suffix']
            if prefix is None:
                prefix = ""
            if suffix is None:
                suffix = ""
        
            c_out = EPG.sub_el(_et_root, 'channel', id=sid)
            EPG.sub_el(c_out, 'display-name', text='%s%s%s %s' %
                (prefix,
                ch_data['display_number'],
                suffix, 
                ch_data['display_name']))
            EPG.sub_el(c_out, 'display-name', text='%s%s%s %s' % 
                (prefix,
                ch_data['display_number'],
                suffix, 
                ch_data['json']['callsign']))
            EPG.sub_el(c_out, 'display-name', text=ch_data['display_number'])
            EPG.sub_el(c_out, 'display-name', text=ch_data['json']['callsign'])
            EPG.sub_el(c_out, 'display-name', text=ch_data['display_name'])

            if self.config['epg']['epg_channel_icon']:
                EPG.sub_el(c_out, 'icon', src=ch_data['thumbnail'])
        return _et_root
    
    def gen_program_xml(self, _et_root, _prog_list):        
        for prog_data in _prog_list:
            prog_out = EPG.sub_el(_et_root, 'programme', 
                start=prog_data['start'], 
                stop=prog_data['stop'], 
                channel=prog_data['channel'])
            if prog_data['title']:
                EPG.sub_el(prog_out, 'title', text=prog_data['title'])
            if prog_data['subtitle']:
                EPG.sub_el(prog_out, 'sub-title', text=prog_data['subtitle'])
            descr_add = ''
            if self.config['epg']['description'] == 'extend':
                
                if prog_data['formatted_date']:
                    descr_add += '(' + prog_data['formatted_date'] + ') '
                if prog_data['genres']:
                    descr_add += ' / '.join(prog_data['genres']) + ' / '
                if prog_data['se_common']:
                    descr_add += prog_data['se_common']
                descr_add += '\n' + prog_data['desc']
            elif self.config['epg']['description'] == 'brief':
                descr_add = prog_data['short_desc']
            elif self.config['epg']['description'] == 'normal':
                descr_add = prog_data['desc']
            else:
                self.logger.warning('Config value [epg][description] is invalid: '
                                    + self.config['epg']['description'])
            EPG.sub_el(prog_out, 'desc', text=descr_add)

            if prog_data['video_quality']:
                video_out = EPG.sub_el(prog_out, 'video')
                EPG.sub_el(video_out, 'quality', prog_data['video_quality'])

            if prog_data['air_date']:
                EPG.sub_el(prog_out, 'date', lang='en',
                    text=prog_data['air_date'])

            EPG.sub_el(prog_out, 'length', units='minutes', text=str(prog_data['length']))
            
            if prog_data['genres']:
                for f in prog_data['genres']:
                    if self.config['epg']['genre'] == 'normal':
                        pass
                    elif self.config['epg']['genre'] == 'tvheadend':
                        if f in epg_category.TVHEADEND.keys():
                            f = epg_category.TVHEADEND[f]
                    else:
                        self.logger.warning('Config value [epg][genre] is invalid: '
                            + self.config['epg']['genre'])
                    EPG.sub_el(prog_out, 'category', lang='en', text=f.strip())

            if prog_data['icon'] and self.config['epg']['epg_program_icon']:
                EPG.sub_el(prog_out, 'icon', src=prog_data['icon'])

            if prog_data['rating']:
                r = ElementTree.SubElement(prog_out, 'rating')
                EPG.sub_el(r, 'value', text=prog_data['rating'])

            if prog_data['se_common']:
                EPG.sub_el(prog_out, 'episode-num', system='common',
                    text=prog_data['se_common'])
                EPG.sub_el(prog_out, 'episode-num', system='xmltv_ns',
                    text=prog_data['se_xmltv_ns'])
                EPG.sub_el(prog_out, 'episode-num', system='SxxExx',
                    text=prog_data['se_common'])

            if prog_data['is_new']:
                EPG.sub_el(prog_out, 'new')

    @staticmethod
    def gen_header_xml():
        xml_out = ElementTree.Element('tv')
        xml_out.set('source-info-url', 'https://www.locast.org')
        xml_out.set('source-info-name', 'locast.org')
        xml_out.set('generator-info-name', 'locastepg')
        xml_out.set('generator-info-url', 'github.com/rocky4546/tvheadend-locast')
        xml_out.set('generator-special-thanks', 'locast2plex')
        return xml_out

    @staticmethod
    def sub_el(_parent, _name, _text=None, **kwargs):
        el = ElementTree.SubElement(_parent, _name, **kwargs)
        if _text:
            el.text = _text
        return el

# pylama:ignore=E722
import os
import time
import datetime
import json
import pathlib
import logging
import urllib.parse
import urllib.request
import urllib.error
import xml.dom.minidom as minidom
from xml.etree import ElementTree

import lib.tvheadend.stations as stations
import lib.tvheadend.utils as utils
from lib.l2p_tools import clean_exit
from lib.filelock import FileLock
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
        xml_out = self.gen_header_xml()
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
            c_out = self.sub_el(_et_root, 'channel', id=sid)
            self.sub_el(c_out, 'display-name', text='%s%s%s %s' %
                (self.config['epg']['epg_prefix'],
                ch_data['display_number'],
                self.config['epg']['epg_suffix'], 
                ch_data['display_name']))
            self.sub_el(c_out, 'display-name', text='%s%s%s %s' % 
                (self.config['epg']['epg_prefix'],
                ch_data['display_number'],
                self.config['epg']['epg_suffix'], 
                ch_data['json']['callsign']))
            self.sub_el(c_out, 'display-name', text=ch_data['display_number'])
            self.sub_el(c_out, 'display-name', text=ch_data['json']['callsign'])
            self.sub_el(c_out, 'display-name', text=ch_data['display_name'])

            if self.config['locast']['epg_channel_icon']:
                self.sub_el(c_out, 'icon', src=ch_data['thumbnail'])
        return _et_root
    
    def gen_program_xml(self, _et_root, _prog_list):        
        for prog_data in _prog_list:
            prog_out = self.sub_el(_et_root, 'programme', 
                start=prog_data['start'], 
                stop=prog_data['stop'], 
                channel=prog_data['channel'])
            if prog_data['title']:
                self.sub_el(prog_out, 'title', text=prog_data['title'])
            if prog_data['subtitle']:
                self.sub_el(prog_out, 'sub-title', text=prog_data['subtitle'])
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
            self.sub_el(prog_out, 'desc', text=descr_add)

            if prog_data['video_quality']:
                video_out = self.sub_el(prog_out, 'video')
                self.sub_el(video_out, 'quality', prog_data['video_quality'])

            if prog_data['air_date']:
                self.sub_el(prog_out, 'date', lang='en',
                    text=prog_data['air_date'])

            self.sub_el(prog_out, 'length', units='minutes', text=str(prog_data['length']))
            
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
                    self.sub_el(prog_out, 'category', lang='en', text=f.strip())

            if prog_data['icon'] and self.config['locast']['epg_program_icon']:
                self.sub_el(prog_out, 'icon', src=prog_data['icon'])

            if prog_data['rating']:
                r = ElementTree.SubElement(prog_out, 'rating')
                self.sub_el(r, 'value', text=prog_data['rating'])

            if prog_data['se_common']:
                self.sub_el(prog_out, 'episode-num', system='common',
                    text=prog_data['se_common'])
                self.sub_el(prog_out, 'episode-num', system='xmltv_ns',
                    text=prog_data['se_xmltv_ns'])
                self.sub_el(prog_out, 'episode-num', system='SxxExx',
                    text=prog_data['se_common'])

            if prog_data['is_new']:
                self.sub_el(prog_out, 'new')

    def gen_header_xml(self):
        xml_out = ElementTree.Element('tv')
        xml_out.set('source-info-url', 'https://www.locast.org')
        xml_out.set('source-info-name', 'locast.org')
        xml_out.set('generator-info-name', 'locastepg')
        xml_out.set('generator-info-url', 'github.com/rocky4546/tvheadend-locast')
        xml_out.set('generator-special-thanks', 'locast2plex')
        return xml_out

    def sub_el(self, parent, name, text=None, **kwargs):
        el = ElementTree.SubElement(parent, name, **kwargs)
        if text:
            el.text = text
        return el

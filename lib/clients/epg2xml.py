# pylama:ignore=E722
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

import logging
import xml.dom.minidom as minidom
from xml.etree import ElementTree

import lib.common.utils as utils
import lib.tvheadend.epg_category as epg_category
from lib.common.decorators import getrequest
from lib.db.db_channels import DBChannels
from lib.db.db_epg import DBepg
from lib.web.pages.templates import web_templates




@getrequest.route('/xmltv.xml')
def xmltv_xml(_tuner):
    try:
        epg = EPG(_tuner)
        reply_str = epg.get_epg_xml(_tuner)
    except MemoryError as e:
        self.do_mime_response(501, 'text/html', 
            web_templates['htmlError'].format('501 - MemoryError: {}'.format(e)))
        



class EPG:
    # https://github.com/XMLTV/xmltv/blob/master/xmltv.dtd
    def __init__(self, _tuner):
        self.logger = logging.getLogger(__name__)
        self.tuner = _tuner
        self.config = _tuner.plugins.config_obj.data
        self.epg_db = DBepg(self.config)
        self.channels_db = DBChannels(self.config)
        self.plugins = _tuner.plugins
        self.namespace = _tuner.query_data['name']
        self.instance = _tuner.query_data['instance']

    def get_epg_xml(self, _tuner):
        try:
            _tuner.do_dict_response({
                'code': 200,
                'headers': {'Content-type': 'application/xml; Transfer-Encoding: chunked'},
                'text': None})

            self.plugins.refresh_epg(self.namespace, self.instance)
            xml_out = self.gen_header_xml()
            channel_list = self.channels_db.get_channels(self.namespace, self.instance)
            self.gen_channel_xml(xml_out, channel_list)
            self.write_xml(xml_out, keep_xml_prolog=True)
            xml_out = None

            self.epg_db.init_get_query(self.namespace, self.instance)
            day_data, ns, inst = self.epg_db.get_next_row()
            self.prog_processed = []
            while day_data:
                xml_out = self.gen_minimal_header_xml()
                self.gen_program_xml(xml_out, day_data, channel_list, ns, inst)
                self.write_xml(xml_out)
                day_data, ns, inst = self.epg_db.get_next_row()
            self.tuner.wfile.write(b'</tv>')
        except MemoryError as e:
            self.logger.error('MemoryError parsing large xml')
            raise e
        xml_out = None

    def write_xml(self, _xml, keep_xml_prolog=False):
        if self.config['epg']['epg_prettyprint']:
            if not keep_xml_prolog:
                epg_dom = ElementTree.tostring(_xml)
                if len(epg_dom) < 20:
                    return
                epg_dom = minidom.parseString(epg_dom).toprettyxml()[27:-6]
            else:
                epg_dom = minidom.parseString(ElementTree.tostring(_xml, encoding='UTF-8', method='xml')).toprettyxml()[:-6]
            self.tuner.wfile.write(epg_dom.encode())
        else:
            if not keep_xml_prolog:
                epg_dom = ElementTree.tostring(_xml)[4:-5]
                if len(epg_dom) < 10:
                    return
            else:
                epg_dom = ElementTree.tostring(_xml)[:-5]
            self.tuner.wfile.write(epg_dom+b'\r\n')
        epg_dom = None

    def gen_channel_xml(self, _et_root, _channel_list):
        sids_processed = []
        for sid, sid_data_list in _channel_list.items():
            if sid in sids_processed:
                continue
            sids_processed.append(sid)
            for ch_data in sid_data_list:
                if not ch_data['enabled']:
                    break
                updated_chnum = utils.wrap_chnum(
                    ch_data['display_number'], ch_data['namespace'],
                    ch_data['instance'], self.config)
                c_out = EPG.sub_el(_et_root, 'channel', id=sid)
                EPG.sub_el(c_out, 'display-name', _text='%s %s' %
                    (updated_chnum, ch_data['display_name']))
                EPG.sub_el(c_out, 'display-name', _text='%s %s' % 
                    (updated_chnum, ch_data['json']['callsign']))
                EPG.sub_el(c_out, 'display-name', _text=ch_data['display_number'])
                EPG.sub_el(c_out, 'display-name', _text=ch_data['json']['callsign'])
                EPG.sub_el(c_out, 'display-name', _text=ch_data['display_name'])

                if self.config['epg']['epg_channel_icon']:
                    EPG.sub_el(c_out, 'icon', src=ch_data['thumbnail'])
                break
        return _et_root
    
    def gen_program_xml(self, _et_root, _prog_list, _channel_list, _ns, _inst):
        for prog_data in _prog_list:
            proginfo = prog_data['start']+prog_data['channel']
            if proginfo in self.prog_processed:
                continue
            skip = False
            for ch_data in _channel_list[prog_data['channel']]:
                if ch_data['namespace'] == _ns \
                        and ch_data['instance'] == _inst \
                        and not ch_data['enabled']:
                    skip = True
                    break
            if skip:
                continue
            self.prog_processed.append(proginfo)
    
            prog_out = EPG.sub_el(_et_root, 'programme', 
                start=prog_data['start'], 
                stop=prog_data['stop'], 
                channel=prog_data['channel'])
            if prog_data['title']:
                EPG.sub_el(prog_out, 'title', lang='en', _text=prog_data['title'])
            if prog_data['subtitle']:
                EPG.sub_el(prog_out, 'sub-title', lang='en', _text=prog_data['subtitle'])
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
            EPG.sub_el(prog_out, 'desc', lang='en', _text=descr_add)

            if prog_data['video_quality']:
                video_out = EPG.sub_el(prog_out, 'video')
                EPG.sub_el(video_out, 'quality', prog_data['video_quality'])

            if prog_data['air_date']:
                EPG.sub_el(prog_out, 'date',
                    _text=prog_data['air_date'])

            EPG.sub_el(prog_out, 'length', units='minutes', _text=str(prog_data['length']))
            
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
                    EPG.sub_el(prog_out, 'category', lang='en', _text=f.strip())

            if prog_data['icon'] and self.config['epg']['epg_program_icon']:
                EPG.sub_el(prog_out, 'icon', src=prog_data['icon'])

            if prog_data['rating']:
                r = ElementTree.SubElement(prog_out, 'rating')
                EPG.sub_el(r, 'value', _text=prog_data['rating'])

            if prog_data['se_common']:
                EPG.sub_el(prog_out, 'episode-num', system='common',
                    _text=prog_data['se_common'])
                EPG.sub_el(prog_out, 'episode-num', system='xmltv_ns',
                    _text=prog_data['se_xmltv_ns'])
                EPG.sub_el(prog_out, 'episode-num', system='SxxExx',
                    _text=prog_data['se_common'])

            if prog_data['is_new']:
                EPG.sub_el(prog_out, 'new')
            else:
                EPG.sub_el(prog_out, 'previously-shown')
            if prog_data['cc']:
                EPG.sub_el(prog_out, 'subtitles', type='teletext')
            if prog_data['premiere']:
                EPG.sub_el(prog_out, 'premiere')

    def gen_header_xml(self):
        if self.namespace is None:
            website = utils.CABERNET_URL
            name = utils.CABERNET_NAME
        else:
            website = self.plugins.plugins[self.namespace].plugin_settings['website']
            name = self.plugins.plugins[self.namespace].plugin_settings['name']
        
        xml_out = ElementTree.Element('tv')
        xml_out.set('source-info-url', website)
        xml_out.set('source-info-name', name)
        xml_out.set('generator-info-name', utils.CABERNET_NAME)
        xml_out.set('generator-info-url', utils.CABERNET_URL)
        xml_out.set('generator-special-thanks', 'locast2plex')
        return xml_out

    def gen_minimal_header_xml(self):
        return ElementTree.Element('tv')


    @staticmethod
    def sub_el(_parent, _name, _text=None, **kwargs):
        el = ElementTree.SubElement(_parent, _name, **kwargs)
        if _text:
            el.text = _text
        return el

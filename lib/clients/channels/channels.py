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

from io import StringIO
from xml.sax.saxutils import escape

import lib.common.utils as utils
from lib.clients.channels.templates import ch_templates
from lib.common.decorators import getrequest
from lib.db.db_channels import DBChannels


@getrequest.route('/playlist')
def playlist(_tuner):
    _tuner.send_response(302)
    _tuner.send_header('Location', _tuner.path.replace('playlist', 'channels.m3u'))
    _tuner.end_headers()


@getrequest.route('/channels.m3u')
def channels_m3u(_tuner):
    _tuner.plugins.refresh_channels(_tuner.query_data['name'])
    _tuner.do_mime_response(200, 'audio/x-mpegurl', get_channels_m3u(
        _tuner.config, _tuner.stream_url, 
        _tuner.query_data['name'], 
        _tuner.query_data['instance']))


def get_channels_m3u(_config, _base_url, _namespace, _instance):

    format_descriptor = '#EXTM3U'
    record_marker = '#EXTINF'

    db = DBChannels(_config)
    ch_data = db.get_channels(_namespace, _instance)
    fakefile = StringIO()
    fakefile.write(
            '%s\n' % format_descriptor
        )

    for sid, sid_data in ch_data.items():
        # NOTE tvheadend supports '|' separated names in two attributes
        # either 'group-title' or 'tvh-tags'
        # if a ';' is used in group-title, tvheadend will use the 
        # entire string as a tag
        groups = sid_data['namespace']
        if sid_data['json']['groups_other']:
            groups += '|' + '|'.join(sid_data['json']['groups_other'])
        if sid_data['json']['HD']:
            if sid_data['json']['group_hdtv']:
                groups += '|' + sid_data['json']['group_hdtv']
        elif sid_data['json']['group_sdtv']:
            groups += '|' + sid_data['json']['group_sdtv']

        fakefile.write(
            '%s\n' % (
                record_marker + ':-1' + ' ' +
                'channelID=\'' + sid + '\' ' +
                'tvg-num=\'' + sid_data['number'] + '\' ' +
                'tvg-chno=\'' + sid_data['number'] + '\' ' +
                'tvg-name=\'' + sid_data['display_name'] + '\' ' +
                'tvg-id=\'' + sid + '\' ' +
                (('tvg-logo=\'' + sid_data['thumbnail'] + '\' ')
                    if sid_data['thumbnail'] else '') +
                'group-title=\''+groups+'\',' + set_service_name(_config, sid_data)
            )
        )
        fakefile.write(
            '%s\n' % (
                (
                    '%s%s/%s/watch/%s' %
                    ('http://', _base_url, sid_data['namespace'], str(sid))
                )
            )
        )
    return fakefile.getvalue()
    

@getrequest.route('/lineup.json')
def lineup_json(_tuner):
    _tuner.plugins.refresh_channels(_tuner.query_data['name'])
    _tuner.do_mime_response(200, 'application/json', get_channels_json(
        _tuner.config, _tuner.stream_url, _tuner.query_data['name'], _tuner.query_data['instance']))

    
def get_channels_json(_config, _base_url, _namespace, _instance):
    db = DBChannels(_config)
    ch_data = db.get_channels(_namespace, _instance)
    return_json = ''
    for sid, sid_data in ch_data.items():
        return_json = return_json + \
            ch_templates['jsonLineup'].format(
                sid_data['number'],
                sid_data['display_name'],
                _base_url + '/' + sid_data['namespace'] + '/watch/' + sid,
                sid_data['json']['HD'])
        return_json = return_json + ','
    return "[" + return_json[:-1] + "]"


@getrequest.route('/lineup.xml')
def lineup_xml(_tuner):
    _tuner.plugins.refresh_channels(_tuner.query_data['name'])
    _tuner.do_mime_response(200, 'application/xml', get_channels_xml(
        _tuner.config, _tuner.stream_url, _tuner.query_data['name'], 
        _tuner.query_data['instance']))


def get_channels_xml(_config, _base_url, _namespace, _instance):
    db = DBChannels(_config)
    ch_data = db.get_channels(_namespace, _instance)
    return_xml = ''
    for sid, sid_data in ch_data.items():
        return_xml = return_xml + \
            ch_templates['xmlLineup'].format(
                sid_data['number'],
                escape(sid_data['display_name']),
                _base_url + '/' + sid_data['namespace'] + '/watch/' + sid,
                sid_data['json']['HD'])
    return "<Lineup>" + return_xml + "</Lineup>"


# returns the service name used to sync with the EPG channel name
def set_service_name(_config, _sid_data):
    updated_chnum = utils.wrap_chnum(
        str(_sid_data['number']), _sid_data['namespace'], _config)
    service_name = updated_chnum + \
        ' ' + _sid_data['display_name']
    return service_name

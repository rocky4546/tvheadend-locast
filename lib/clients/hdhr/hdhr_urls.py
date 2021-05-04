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

from .templates import hdhr_templates
from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
import lib.common.utils as utils

from lib.web.pages.templates import web_templates


@getrequest.route('/discover.json')
def discover_json(_tuner):
    ns_inst_path = _tuner.get_ns_inst_path(_tuner.query_data)
    if _tuner.query_data['name'] is None:
        name = ''
    else:
        name = _tuner.query_data['name']+' '
        
    namespace = None
    for area, area_data in _tuner.config.items():
        if 'player-tuner_count' in area_data.keys():
            namespace = area

    _tuner.do_mime_response(200,
        'application/json',
        hdhr_templates['jsonDiscover'].format(
            name+_tuner.config['hdhomerun']['reporting_friendly_name'],
            _tuner.config['hdhomerun']['reporting_model'],
            _tuner.config['hdhomerun']['reporting_firmware_name'],
            _tuner.config['main']['version'],
            _tuner.config['hdhomerun']['hdhr_id'],
            _tuner.config[namespace]['player-tuner_count'],
            _tuner.web_admin_url, ns_inst_path))


@getrequest.route('/device.xml')
def device_xml(_tuner):
    if _tuner.query_data['name'] is None:
        name = ''
    else:
        name = _tuner.query_data['name']+' '
    _tuner.do_mime_response(200,
        'application/xml',
        hdhr_templates['xmlDevice'].format(
            name+_tuner.config['hdhomerun']['reporting_friendly_name'],
            _tuner.config['hdhomerun']['reporting_model'],
            _tuner.config['hdhomerun']['hdhr_id'],
            _tuner.config['main']['uuid'],
            utils.CABERNET_URL
        ))


@getrequest.route('/lineup_status.json')
def lineup_status_json(_tuner):
    # Assumes only one scan can be active at a time.
    if _tuner.scan_state < 0:
        return_json = hdhr_templates['jsonLineupStatusIdle'] \
            .replace("Antenna", _tuner.config['hdhomerun']['tuner_type'])
    else:
        _tuner.scan_state += 20
        if _tuner.scan_state > 100:
            _tuner.scan_state = 100
        num_of_channels = len(_tuner.channels_db.get_channels(_tuner.query_data['name'], None))
        return_json = hdhr_templates['jsonLineupStatusScanning'].format(
            _tuner.scan_state,
            int(num_of_channels * _tuner.scan_state / 100))

        if _tuner.scan_state == 100:
            _tuner.scan_state = -1
            _tuner.update_scan_status(_tuner.query_data['name'], 'Idle')
    _tuner.do_mime_response(200, 'application/json', return_json)


@postrequest.route('/lineup.post')
def lineup_post(_tuner):
    if _tuner.query_data['scan'] == 'start':
        _tuner.scan_state = 0
        _tuner.update_scan_status(_tuner.query_data['name'], 'Scan')
        _tuner.do_mime_response(200, 'text/html')
    elif _tuner.query_data['scan'] == 'abort':
        _tuner.do_mime_response(200, 'text/html')
        _tuner.scan_state = -1
        _tuner.update_scan_status(_tuner.query_data['name'], 'Idle')
    else:
        _tuner.logger.warning("Unknown scan command " + _tuner.query_data['scan'])
        _tuner.do_mime_response(400, 'text/html',
            web_templates['htmlError'].format(
                _tuner.query_data['scan'] + ' is not a valid scan command'))

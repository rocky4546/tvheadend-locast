import lib.tvheadend.stations as stations
from io import StringIO


def get_channels_m3u(_config, _base_url):

    format_descriptor = '#EXTM3U'
    record_marker = '#EXTINF'

    fakefile = StringIO()
    fakefile.write(
            '%s\n' % format_descriptor
        )
    stations_obj = stations.Stations()
    station_list = stations_obj.get_dma_stations_and_channels()

    for sid in station_list:
        fakefile.write(
            '%s\n' % (
                record_marker + ':-1' + ' ' +
                'channelID=\'' + sid + '\' ' +
                'tvg-num=\'' + station_list[sid]['channel'] + '\' ' +
                'tvg-chno=\'' + station_list[sid]['channel'] + '\' ' +
                'tvg-name=\'' + station_list[sid]['friendlyName'] + '\' ' +
                'tvg-id=\'' + sid + '\' ' +
                (('tvg-logo=\'' + station_list[sid]['logoUrl'] + '\' ')
                    if 'logoUrl' in station_list[sid].keys() else '') +
                'group-title=\'Locast\',' + set_service_name(_config, station_list, sid)
            )
        )
        fakefile.write(
            '%s\n' % (
                (
                    '%s%s/watch/%s' %
                    ('http://', _base_url, str(sid))
                )
            )
        )
    return fakefile.getvalue()
    

# returns the service name used to sync with the EPG channel name
def set_service_name(config, station_list, sid):
    service_name = config['epg']['epg_prefix'] + \
        str(station_list[sid]['channel']) + \
        config['epg']['epg_suffix'] + \
        ' ' + station_list[sid]['friendlyName']
    return service_name

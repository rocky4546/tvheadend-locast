# from https://github.com/deathbybandaid/fHDHR_Locast/blob/master/fHDHR/fHDHRweb/fHDHRdevice/channels_m3u.py
import lib.stations as stations
from io import StringIO


def get_channels_m3u(config, location, base_url):

    FORMAT_DESCRIPTOR = '#EXTM3U'
    RECORD_MARKER = '#EXTINF'

    fakefile = StringIO()

    xmltvurl = ('%s%s/xmltv.xml' % ('http://', base_url))

    fakefile.write(
            '%s\n' % (FORMAT_DESCRIPTOR)
        )
    station_list = stations.get_dma_stations_and_channels(config, location)
    index = 1

    for sid in station_list:
        fakefile.write(
            '%s\n' % (
                RECORD_MARKER + ':-1,'+ index + ' ' +
                'channelID=\'' + str(sid) + '\' ' +
                'tvg-num=\'' + str(station_list[sid]['channel']) + '\' ' +
                'tvg-chno=\'' + str(station_list[sid]['channel']) + '\' ' +
                'tvg-name=\'' + station_list[sid]['friendlyName'] + '\' ' +
                'tvg-id=\'' + str(sid) + '\' ' +
                (('tvg-logo=\'' + station_list[sid]['logoUrl'] + '\' ') if 'logoUrl' in station_list[sid].keys() else '') +
                'group-title=\'Locast\',' + set_service_name(config, station_list, sid)  #CAM
            )
        )
        fakefile.write(
            '%s\n' % (
                (
                    '%s%s/watch/%s' %
                    ('http://', base_url, str(sid))
                )
            )
        )
        index += 1
    return fakefile.getvalue()
    
####### CAM CAM CAM CAM new procedure
# returns the service name used to sync with the EPG channel name
def set_service_name(config, station_list, sid):
    service_name = config['epg']['epg_prefix'] + \
        str(station_list[sid]['channel']) + \
        config['epg']['epg_suffix'] + \
        ' ' + station_list[sid]['friendlyName']  #CAM
    return service_name
    ###### CAM End of method

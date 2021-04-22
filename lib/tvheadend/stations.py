import time
import urllib
from urllib import request
import ssl
import zipfile
import os
import datetime
import json
import pathlib
import logging

from lib.l2p_tools import clean_exit
from lib.filelock import FileLock
from lib.dma_markets import get_dma_info
import lib.tvheadend.utils as utils

fcc_ssl_context = ssl.SSLContext()
fcc_ssl_context.set_ciphers('HIGH:!DH:!aNULL')


def stations_process(_config, _locast, _location):
    try:
        while True:
            Stations.config = _config
            Stations.locast = _locast
            Stations.location = _location
            stations = Stations()
            stations.refresh_dma_stations_and_channels()
            time.sleep(_config["locast"]["fcc_timeout"])
            # Work in eastern time, since that is what the FCC is using to determine maintenance times
            current_time = datetime.datetime.now(tz=EST5EDT())
            # if we find we're returning from delay at a time that the FCC is doing maintenance, sleep a bit more...
            if (current_time.hour >= 3) and (current_time.hour <= 5):
                # get the exact time we need to wait until we can grab the FCC data
                sleep_time = ((6 - current_time.hour) * 60 * 60)
                sleep_time = (sleep_time - (current_time.minute + 60))
                sleep_time = (sleep_time - current_time.second)
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        clean_exit()


def check_station_file(_config, _location):
    filepath = _location["DMA"] + "_stations.json"
    filepath = pathlib.Path(_config["paths"]["stations_dir"]).joinpath(filepath)
    if os.path.exists(filepath):
        return True
    else:
        return False


class Stations:
    config = None
    locast = None
    location = None
    dma_channels = None

    def __init__(self, *args):
        self.logger = logging.getLogger(__name__)

    def refresh_dma_stations_and_channels(self):
        filepath = Stations.location["DMA"] + "_stations.json"
        filepath = pathlib.Path(Stations.config["paths"]["stations_dir"]).joinpath(filepath)
        if utils.is_file_expired(filepath, days=7):
            fcc_stations = self.get_fcc_stations()
            Stations.dma_channels = self.generate_dma_stations_and_channels_file(fcc_stations)

    def get_online_file_time(self, _facility_url):
        url_head = urllib.request.Request(_facility_url, method='HEAD')
        resp = urllib.request.urlopen(url_head, context=fcc_ssl_context)
        online_file_time = resp.headers['last-modified'].replace(" GMT", "")
        online_file_time = datetime.datetime.strptime(online_file_time, '%a, %d %b %Y %H:%M:%S')
        online_file_time = online_file_time.replace(tzinfo=EST5EDT()).astimezone(datetime.timezone.utc)
        return online_file_time

    def get_offline_file_time(self, _facility_zip_dl_path):
        offline_file_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(_facility_zip_dl_path))
        offline_file_time = offline_file_time.replace(tzinfo=datetime.timezone.utc)
        return offline_file_time

    def fcc_db_format(self, _fac_line):
        current_date = datetime.datetime.utcnow()

        clean_line = _fac_line.strip()
        fac_line_split = clean_line.split('|')

        fac_template = {
            "comm_city": "",
            "comm_state": "",
            "eeo_rpt_ind": "",
            "fac_address1": "",
            "fac_address2": "",
            "fac_callsign": "",
            "fac_channel": "",
            "fac_city": "",
            "fac_country": "",
            "fac_frequency": "",
            "fac_service": "",
            "fac_state": "",
            "fac_status_date": "",
            "fac_type": "",
            "facility_id": "",
            "lic_expiration_date": "",
            "fac_status": "",
            "fac_zip1": "",
            "fac_zip2": "",
            "station_type": "",
            "assoc_facility_id": "",
            "callsign_eff_date": "",
            "tsid_ntsc": "",
            "tsid_dtv": "",
            "digital_status": "",
            "sat_tv": "",
            "network_affil": "",
            "nielsen_dma": "",
            "tv_virtual_channel": "",
            "last_change_date": "",
            "end_of_record": "",
        }
        formatteddict = {}
        key_num = 0
        for fcc_key in list(fac_template.keys()):
            insert_value = None
            if fac_line_split[key_num] != '':
                insert_value = fac_line_split[key_num]
            formatteddict[fcc_key] = insert_value
            key_num += 1

        # Check if expired
        if (not formatteddict['fac_status'] or formatteddict['fac_status'] != 'LICEN'
                or not formatteddict['lic_expiration_date']):
            return None

        fac_lic_expiration_date_split = formatteddict["lic_expiration_date"].split('/')
        fac_lic_expiration_date_datetime = datetime.datetime(int(fac_lic_expiration_date_split[2]),
            int(fac_lic_expiration_date_split[0]),
            int(fac_lic_expiration_date_split[1]),
            23, 59, 59, 999999)
        if fac_lic_expiration_date_datetime < current_date:
            return None

        # Check if we have a correct signal type
        if formatteddict['fac_service'] not in ['DT', 'TX', 'TV', 'TB', 'LD', 'DC']:
            return None

        return formatteddict

    def get_fcc_stations(self):

        fcc_cache_dir = pathlib.Path(Stations.config["paths"]["stations_dir"])

        facility_url = 'https://transition.fcc.gov/ftp/Bureaus/MB/Databases/cdbs/facility.zip'
        facility_zip_dl_path = pathlib.Path(fcc_cache_dir).joinpath("facility.zip")
        fcc_unzipped_dat = pathlib.Path(fcc_cache_dir).joinpath("facility.dat")
        fcc_cached_file = pathlib.Path(fcc_cache_dir).joinpath("tv_facilities.json")
        fcc_cached_file_lock = pathlib.Path(fcc_cache_dir).joinpath("tv_facilities.json.lock")

        why_download = None
        facility_list = []

        if not os.path.exists(facility_zip_dl_path):
            why_download = "FCC facilities database cache missing."
        else:
            self.logger.debug("Checking FCC facilities database for updates.")

            offline_file_time = self.get_offline_file_time(facility_zip_dl_path)
            online_file_time = self.get_online_file_time(facility_url)




            if not offline_file_time <= online_file_time:
                self.logger.debug("Cached facilities database is current.")
            else:
                why_download = "Online facilities database is newer."

        if why_download:
            self.logger.info(why_download + ' Downloading the latest FCC facilities database...')

            # remove old copies of zip and dat
            if os.path.exists(facility_zip_dl_path):
                os.remove(facility_zip_dl_path)
            if os.path.exists(fcc_unzipped_dat):
                os.remove(fcc_unzipped_dat)

            if not os.path.exists(facility_zip_dl_path):
                with urllib.request.urlopen(facility_url, context=fcc_ssl_context) as fcc_facility_net:
                    fcc_facility_data = fcc_facility_net.read()

                with open(facility_zip_dl_path, 'wb') as fcc_facility_file:
                    fcc_facility_file.write(fcc_facility_data)

            if (not os.path.exists(fcc_unzipped_dat)) and (os.path.exists(facility_zip_dl_path)):
                self.logger.debug('Unzipping FCC facilities database...')

                with zipfile.ZipFile(facility_zip_dl_path, 'r') as zip_ref:
                    zip_ref.extractall(fcc_cache_dir)

            # make sure the fcc data is not corrupted (if the file isn't as big as we expect)
            if os.path.exists(fcc_unzipped_dat) and os.path.getsize(fcc_unzipped_dat) > 7000000:

                self.logger.debug('Reading and formatting FCC database...')

                with open(fcc_unzipped_dat, "r") as fac_file:
                    lines = fac_file.readlines()

                for fac_line in lines:
                    formatteddict = self.fcc_db_format(fac_line)
                    if formatteddict:
                        facility_list.append(formatteddict)

                self.logger.debug('Found ' + str(len(facility_list)) + ' stations.')

                facility_json = {
                    "fcc_station_list": facility_list
                }

                json_file_lock = FileLock(fcc_cached_file_lock)

                with json_file_lock:
                    if os.path.exists(fcc_cached_file):
                        os.remove(fcc_cached_file)

                    with open(fcc_cached_file, "w") as write_file:
                        json.dump(facility_json, write_file, indent=4, sort_keys=True)

            return facility_list

        else:
            json_file_lock = FileLock(fcc_cached_file_lock)

            with json_file_lock:
                with open(fcc_cached_file, "r") as fcc_station_file_obj:
                    fcc_stations = json.load(fcc_station_file_obj)

            return fcc_stations["fcc_station_list"]

    def generate_dma_stations_and_channels_file(self, _fcc_stations):
        station_list = Stations.locast.get_stations()
        final_channel_list = {}
        self.logger.info("Found " + str(len(station_list)) + " stations for DMA " + str(Stations.location["DMA"]))

        fcc_market = get_dma_info(str(Stations.location["DMA"]))
        if not len(fcc_market):
            self.logger.info("No DMA to FCC mapping found.  Poke the developer to get it into locast2plex.")

        none_channel = 1000

        for index, locast_station in enumerate(station_list):

            sid = str(locast_station['id'])
            final_channel_list[sid] = {'callSign': locast_station['name']}

            if 'logo226Url' in locast_station.keys():
                final_channel_list[sid]['logoUrl'] = locast_station['logo226Url']
            elif 'logoUrl' in locast_station.keys():
                final_channel_list[sid]['logoUrl'] = locast_station['logoUrl']

            if 'videoProperties' in locast_station['listings'][0]:
                if 'HD' in locast_station['listings'][0]['videoProperties']:
                    final_channel_list[sid]['HD'] = 1

            # check if this is a [channel] [station name] result in the callsign
            # whether the first char is a number (checking for result like "2.1 CBS")
            try:
                # if number, get the channel and name -- we're done!
                # Check if the the callsign has a float (x.x) value. Save as a
                # string though, to preserve any trailing 0s

                assert (float(locast_station['callSign'].split()[0]))
                final_channel_list[sid]['channel'] = locast_station['callSign'].split()[0]
                final_channel_list[sid]['friendlyName'] = locast_station['callSign'].split()[1]

            except ValueError:

                self.logger.warning('################### CALLSIGN ERROR: {} {}'.format(sid, locast_station['callSign']))

                # result like "WDPN" or "CBS" in the callsign field, or the callsign in the name field
                # then we'll search the callsign in a few different lists to get the station channel
                # note: callsign field usually has the most recent data if it contains an actual callsign
                skip_sub_id = False

                # callsign from "callsign" field
                callsign_result = self.detect_callsign(locast_station['callSign'])

                # callsign from "name" field - usually in "[callsign][TYPE][subchannel]" format
                # example: WABCDT2
                alt_callsign_result = self.detect_callsign(locast_station['name'])

                # check the known station json that we maintain whenever locast's
                # reported station is iffy
                with open("known_stations.json", "r") as known_stations_file_obj:
                    known_stations = json.load(known_stations_file_obj)

                # first look via "callsign" value
                ks_result = self.find_known_station(locast_station, 'callSign', known_stations)
                if ks_result is not None:
                    final_channel_list[sid]['channel'] = ks_result['channel']
                    skip_sub_id = ks_result['skip_sub']

                # then check "name"
                if 'channel' not in final_channel_list[sid]:
                    ks_result = self.find_known_station(locast_station, 'name', known_stations)
                    if ks_result is not None:
                        final_channel_list[sid]['channel'] = ks_result['channel']
                        skip_sub_id = ks_result['skip_sub']

                # if we couldn't find anything look through fcc list for a match.
                # first by searching the callsign found in the "callsign" field
                if ('channel' not in final_channel_list[sid]) and callsign_result['verified']:
                    for market_item in fcc_market:
                        result = self.find_fcc_station(callsign_result['callsign'], market_item["fcc_dma_str"],
                            _fcc_stations)
                        if result is not None:
                            final_channel_list[sid]['channel'] = result['channel']
                            skip_sub_id = result['analog']
                            break

                # if we still couldn't find it, see if there's a match via the
                # "name" field
                if ('channel' not in final_channel_list[sid]) and alt_callsign_result['verified']:
                    for market_item in fcc_market:
                        result = self.find_fcc_station(alt_callsign_result['callsign'], market_item["fcc_dma_str"],
                            _fcc_stations)
                        if result is not None:
                            final_channel_list[sid]['channel'] = result['channel']
                            skip_sub_id = result['analog']
                            break

                # locast usually adds a number in it's callsign (in either field).  that
                # number is the subchannel
                if (not skip_sub_id) and ('channel' in final_channel_list[sid]):
                    if callsign_result['verified'] and (callsign_result['subchannel'] is not None):
                        final_channel_list[sid]['channel'] = final_channel_list[sid]['channel'] + '.' + callsign_result[
                            'subchannel']
                    elif alt_callsign_result['verified'] and (alt_callsign_result['subchannel'] is not None):
                        final_channel_list[sid]['channel'] = final_channel_list[sid]['channel'] + '.' + \
                                                             alt_callsign_result['subchannel']
                    else:
                        final_channel_list[sid]['channel'] = final_channel_list[sid]['channel'] + '.1'

                # mark stations that did not get a channel, but outside of the normal range.
                # the user will have to weed these out in Plex...
                if 'channel' not in final_channel_list[sid]:
                    final_channel_list[sid]['channel'] = str(none_channel)
                    none_channel = none_channel + 1

                final_channel_list[sid]['friendlyName'] = locast_station['callSign']

        dma_channels_list_path = Stations.location["DMA"] + "_stations.json"
        dma_channels_list_file = pathlib.Path(Stations.config["paths"]["stations_dir"]) \
            .joinpath(dma_channels_list_path)
        dma_channels_list_file_lock = FileLock(str(dma_channels_list_file) + ".lock")

        with dma_channels_list_file_lock:
            with open(dma_channels_list_file, "w") as dma_stations_file:
                json.dump(final_channel_list, dma_stations_file, indent=4)
        return final_channel_list

    def get_dma_stations_and_channels(self):
        if Stations.dma_channels is None:
            channel_list_path = Stations.location["DMA"] + "_stations.json"
            channel_list_file = pathlib.Path(Stations.config["paths"]["stations_dir"]).joinpath(channel_list_path)
            channel_list_file_lock = FileLock(str(channel_list_file) + ".lock")
            with channel_list_file_lock:
                with open(channel_list_file, "r") as dma_stations_file:
                    channel_list = json.load(dma_stations_file)
            Stations.dma_channels = channel_list
            return channel_list
        else:
            return Stations.dma_channels

    def detect_callsign(self, _compare_string):
        verified = False
        station_type = None
        subchannel = None
        back_index = -1

        while _compare_string[back_index].isnumeric():
            back_index = back_index - 1

        # if there is a number, backIndex will be > 1
        if back_index != -1:
            subchannel = _compare_string[(back_index + 1):]
            compare_string = _compare_string[:(back_index + 1)]
        else:
            compare_string = _compare_string

        if len(compare_string) > 4:
            station_type = compare_string[-2:]
            compare_string = compare_string[:-2]

        # verify if text from "callsign" is an actual callsign
        if (((compare_string[0] == 'K')
             or (compare_string[0] == 'W')) and ((len(compare_string) == 3)
                                                 or (len(compare_string) == 4))):
            verified = True

        return {
            "verified": verified,
            "station_type": station_type,
            "subchannel": subchannel,
            "callsign": compare_string
        }

    def find_known_station(self, _station, _search_by, _known_stations):

        for known_station in _known_stations:
            if ((known_station[_search_by] == _station[_search_by])
                    and (known_station['dma'] == _station['dma'])):

                return_channel = known_station['rootChannel']

                if known_station['subChannel'] is not None:
                    return {
                        "channel": return_channel + '.' + known_station['subChannel'],
                        "skip_sub": True
                    }

                elif known_station['analog']:
                    return {
                        "channel": return_channel,
                        "skip_sub": True
                    }

                return {
                    "channel": return_channel,
                    "skip_sub": False
                }

        return None

    def find_fcc_station(self, _callsign, _market, _fcc_stations):
        for fcc_station in _fcc_stations:
            # go through each possible station
            if fcc_station['nielsen_dma'] == _market:
                # split fcc callsign away from it's dash, if one exists, then compare
                compare_callsign = fcc_station['fac_callsign'].split('-')[0]
                if compare_callsign == _callsign:
                    # if we have a callsign match, add the channel
                    if fcc_station['tv_virtual_channel'] != "":
                        return {
                            "channel": fcc_station['tv_virtual_channel'],
                            "analog": False
                        }
                    else:
                        # if we find this to be analog, don't apply subchannel
                        return {
                            "channel": fcc_station['fac_channel'],
                            "analog": True
                        }

        return None


# from http://docs.python.org/library/datetime.html
# via https://stackoverflow.com/questions/11710469/how-to-get-python-to-display-current-time-eastern
class EST5EDT(datetime.tzinfo):

    def utcoffset(self, _dt):
        return datetime.timedelta(hours=-5) + self.dst(_dt)

    def dst(self, dt):
        d = datetime.datetime(dt.year, 3, 8)  # 2nd Sunday in March
        self.dston = d + datetime.timedelta(days=6 - d.weekday())
        d = datetime.datetime(dt.year, 11, 1)  # 1st Sunday in Nov
        self.dstoff = d + datetime.timedelta(days=6 - d.weekday())
        if self.dston <= dt.replace(tzinfo=None) < self.dstoff:
            return datetime.timedelta(hours=1)
        else:
            return datetime.timedelta(0)

    def tzname(self, _dt):
        return 'EST5EDT'

# pylama:ignore=E722
import os
import time
import datetime
import json
import pathlib
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import lib.tvheadend.stations as stations
import lib.tvheadend.utils as utils
from lib.l2p_tools import clean_exit
from lib.filelock import FileLock
import lib.tvheadend.epg_category as epg_category


def epg_process(config, location):
    epg_locast = EPGLocast(config, location)
    epg_locast.run()


class EPGLocast:

    def __init__(self, _config, _location):
        self.config = _config
        self.location = _location
        self.logger = logging.getLogger(__name__)
        stations.Stations.config = _config
        stations.Stations.location = _location
        self.stations = stations.Stations()

    def run(self):
        self.generate_epg_file()
        self.dummy_xml()
        try:
            while True:
                time.sleep(self.config["main"]["epg_update_frequency"])
                self.logger.info('Fetching EPG for DMA ' + str(self.location['DMA']) + '.')
                self.generate_epg_file()
        except KeyboardInterrupt:
            clean_exit()

    def dummy_xml(self):
        out_path = pathlib.Path(self.config["main"]["cache_dir"]) \
            .joinpath(str(self.location["DMA"]) + "_epg").with_suffix(".xml")
        if os.path.exists(out_path):
            return

        self.logger.debug('Creating Temporary Empty XMLTV File.')

        base_cache_dir = self.config["main"]["cache_dir"]

        cache_dir = pathlib.Path(base_cache_dir).joinpath(str(self.location["DMA"]) + "_epg")
        if not cache_dir.is_dir():
            cache_dir.mkdir()

        out = ET.Element('tv')
        out.set('source-info-url', 'https://www.locast.org')
        out.set('source-info-name', 'locast.org')
        out.set('generator-info-name', 'locastepg')
        out.set('generator-info-url', 'github.com/rocky4546/tvheadend-locast')
        with open(out_path, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(ET.tostring(out, encoding='UTF-8'))

    def generate_epg_file(self):

        hd_channel_list = set([])
        base_cache_dir = self.config["main"]["cache_dir"]
        out_path = pathlib.Path(base_cache_dir).joinpath(str(self.location["DMA"]) + "_epg").with_suffix(".xml")
        if not utils.is_file_expired(out_path,
                hours=int(self.config["epg"]["min_refresh_rate"] / 3600)):
            return

        out_lock_path = pathlib.Path(base_cache_dir) \
            .joinpath(str(self.location["DMA"]) + "_epg").with_suffix(".xml.lock")
        cache_dir = pathlib.Path(base_cache_dir).joinpath(str(self.location["DMA"]) + "_epg")
        if not cache_dir.is_dir():
            cache_dir.mkdir()

        dma_channels = self.stations.get_dma_stations_and_channels()
        # Make a date range to pull
        todaydate = datetime.datetime.utcnow() \
            .replace(hour=0, minute=0, second=0, microsecond=0)  # make sure we're dealing with UTC!
        dates_to_pull = [todaydate]
        days_to_pull = int(self.config["main"]["epg_update_days"])
        for x in range(1, days_to_pull - 1):
            xdate = todaydate + datetime.timedelta(days=x)
            dates_to_pull.append(xdate)

        self.remove_stale_cache(cache_dir, todaydate)

        out = ET.Element('tv')
        out.set('source-info-url', 'https://www.locast.org')
        out.set('source-info-name', 'locast.org')
        out.set('generator-info-name', 'locastepg')
        out.set('generator-info-url', 'github.com/rocky4546/tvheadend-locast')
        out.set('generator-special-thanks', 'locast2plex')

        done_channels = False

        # remove today EPG so it will refresh
        file_to_remove = cache_dir.joinpath(todaydate.strftime("%m-%d-%Y") + '.json')
        if file_to_remove.is_file():
            file_to_remove.unlink()

        for x_date in dates_to_pull:
            url = ('https://api.locastnet.org/api/watch/epg/' +
                   str(self.location["DMA"]) + "?startTime=" + x_date.isoformat())

            result = self.get_cached(cache_dir, x_date.strftime("%m-%d-%Y"), url)
            channel_info = json.loads(result)

            # List Channels First
            if not done_channels:
                done_channels = True
                for channel_item in channel_info:
                    sid = str(channel_item['id'])
                    if sid in dma_channels.keys():
                        channel_number = str(dma_channels[sid]['channel'])
                        channel_realname = str(dma_channels[sid]['friendlyName'])
                        channel_callsign = str(dma_channels[sid]['callSign'])

                        channel_logo = None
                        if 'logo226Url' in channel_item.keys():
                            channel_logo = channel_item['logo226Url']
                        elif 'logoUrl' in channel_item.keys():
                            channel_logo = channel_item['logoUrl']

                        c_out = self.sub_el(out, 'channel', id=sid)
                        self.sub_el(c_out, 'display-name', text='%s%s%s %s' %
                            (self.config['epg']['epg_prefix'], channel_number,
                            self.config['epg']['epg_suffix'], channel_callsign))
                        self.sub_el(c_out, 'display-name', text='%s %s %s' % (channel_number, channel_callsign, sid))
                        self.sub_el(c_out, 'display-name', text=channel_number)
                        self.sub_el(c_out, 'display-name', text='%s %s fcc' % (channel_number, channel_callsign))
                        self.sub_el(c_out, 'display-name', text=channel_callsign)
                        self.sub_el(c_out, 'display-name', text=channel_realname)

                        if channel_logo is not None:
                            self.sub_el(c_out, 'icon', src=channel_logo)
                    else:
                        self.logger.debug('EPG: Skipping channel id=%d'.format(sid))

            # Now list Program information
            for channel_item in channel_info:
                sid = str(channel_item['id'])
                if sid in dma_channels.keys():
                    channel_number = str(dma_channels[sid]['channel'])
                    channel_realname = str(dma_channels[sid]['friendlyName'])
                    channel_callsign = str(dma_channels[sid]['callSign'])

                    if 'logo226Url' in channel_item.keys():
                        channel_logo = channel_item['logo226Url']

                    elif 'logoUrl' in channel_item.keys():
                        channel_logo = channel_item['logoUrl']

                    for event in channel_item['listings']:

                        tm_start = utils.tm_parse(event['startTime'])  # this is returned from locast in UTC
                        tm_duration = event['duration'] * 1000
                        tm_end = utils.tm_parse(event['startTime'] + tm_duration)

                        event_genres = []
                        if 'genres' in event.keys():
                            event_genres = event['genres'].split(",")

                        # note we're returning everything as UTC, as the clients handle converting to correct timezone
                        prog_out = self.sub_el(out, 'programme', start=tm_start, stop=tm_end, channel=sid)

                        if event['title']:
                            self.sub_el(prog_out, 'title', lang='en', text=event['title'])

                        if 'movie' in event_genres and event['releaseYear']:
                            self.sub_el(prog_out, 'sub-title', lang='en', text='Movie: ' + event['releaseYear'])
                        elif 'episodeTitle' in event.keys():
                            self.sub_el(prog_out, 'sub-title', lang='en', text=event['episodeTitle'])

                        if 'description' not in event.keys():
                            event['description'] = "Unavailable"
                        elif event['description'] is None:
                            event['description'] = "Unavailable"
                        elif self.config['epg']['description'] == 'extend':
                            # append the date created, original genre and episode info on top line
                            # format (date) genre / episode
                            descr_add = ''
                            date_str = self.date_parse(event, 'releaseDate', '%Y/%m/%d')
                            if date_str is not None:
                                descr_add = descr_add + '(' + date_str + ') '
                            if 'genres' in event.keys():
                                descr_add = descr_add + event['genres'].replace(',', ' /') + ' / '
                            if 'seasonNumber' in event.keys():
                                descr_add = descr_add + 'S' + '{:0>2d}'.format(event['seasonNumber'])
                            if 'episodeNumber' in event.keys():
                                descr_add = descr_add + 'E' + '{:0>3d}'.format(event['episodeNumber'])
                            event['description'] = descr_add + '\n' + event['description']
                        elif self.config['epg']['description'] == 'brief':
                            event['description'] = event['shortDescription']
                        elif self.config['epg']['description'] == 'normal':
                            pass
                        else:
                            self.logger.warning('Config value [epg][description] is invalid: '
                                                + self.config['epg']['description'])
                        self.sub_el(prog_out, 'desc', lang='en', text=event['description'])

                        if 'videoProperties' in event.keys():
                            if 'HD' in event['videoProperties']:
                                video_out = self.sub_el(prog_out, 'video')
                                self.sub_el(video_out, 'quality', 'HDTV')
                                hd_channel_list.add(sid)

                        if 'releaseDate' in event.keys():
                            self.sub_el(prog_out, 'date', lang='en',
                                text=self.date_parse(event, 'releaseDate', '%Y%m%d'))

                        self.sub_el(prog_out, 'length', units='minutes', text=str(event['duration']))

                        for f in event_genres:
                            f = f.strip()
                            if self.config['epg']['genre'] == 'normal':
                                pass
                            elif self.config['epg']['genre'] == 'tvheadend':
                                if f in epg_category.TVHEADEND.keys():
                                    f = epg_category.TVHEADEND[f]
                            else:
                                self.logger.warning('Config value [epg][genre] is invalid: '
                                                    + self.config['epg']['genre'])
                            self.sub_el(prog_out, 'category', lang='en', text=f.strip())
                            self.sub_el(prog_out, 'genre', lang='en', text=f.strip())

                        if event["preferredImage"] is not None:
                            self.sub_el(prog_out, 'icon', src=event["preferredImage"])

                        if 'rating' not in event.keys():
                            event['rating'] = "N/A"
                        r = ET.SubElement(prog_out, 'rating')
                        self.sub_el(r, 'value', text=event['rating'])

                        if 'seasonNumber' in event.keys() and 'episodeNumber' in event.keys():
                            s_ = int(str(event['seasonNumber']), 10)
                            e_ = int(str(event['episodeNumber']), 10)
                            self.sub_el(prog_out, 'episode-num', system='common',
                                text='S%02dE%02d' % (s_, e_))
                            self.sub_el(prog_out, 'episode-num', system='xmltv_ns',
                                text='%d.%d.0' % (int(s_) - 1, int(e_) - 1))
                            self.sub_el(prog_out, 'episode-num', system='SxxExx',
                                text='S%02dE%02d' % (s_, e_))

                        if 'isNew' in event.keys():
                            if event['isNew']:
                                self.sub_el(prog_out, 'new')

                else:
                    self.logger.debug('EPG Skipping channel programming id=%d'.format(sid))

        xml_lock = FileLock(out_lock_path)
        with xml_lock:
            with open(out_path, 'wb') as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(ET.tostring(out, encoding='UTF-8'))

    def get_epg(self):
        epg_path = pathlib.Path(self.config['main']['cache_dir']).joinpath(str(self.location['DMA']) + '_epg.xml')
        if utils.is_file_expired(epg_path,
                hours=int(self.config['epg']['min_refresh_rate'] / 3600)):
            self.generate_epg_file()
        xml_lock = FileLock(str(epg_path) + '.lock')
        with xml_lock:
            with open(epg_path, 'rb') as epg_file:
                return_str = epg_file.read().decode('utf-8')
        return return_str

    def get_cached(self, cache_dir, cache_key, url):
        cache_path = cache_dir.joinpath(cache_key + '.json')
        if cache_path.is_file():
            self.logger.debug('FROM CACHE:' + str(cache_path))
            with open(cache_path, 'rb') as f:
                return f.read()
        else:
            self.logger.debug('Fetching:  ' + url)
            try:
                resp = urllib.request.urlopen(url)
                result = resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 400:
                    self.logger.debug('Got a 400 error!  Ignoring it.')
                    result = (
                        b'{'
                        b'"note": "Got a 400 error at this time, skipping.",'
                        b'"channels": []'
                        b'}')
                else:
                    raise
            with open(cache_path, 'wb') as f:
                f.write(result)
            return result

    def remove_stale_cache(self, cache_dir, todaydate):
        for p in cache_dir.glob('*'):
            try:
                cachedate = datetime.datetime.strptime(str(p.name).replace('.json', ''), '%m-%d-%Y')
                if cachedate >= todaydate:
                    continue
            except Exception:
                pass
            self.logger.debug('Removing stale cache file:' + p.name)
            p.unlink()

    def date_parse(self, event, key, format_str):
        dt_str = None
        if key not in event.keys() or event[key] is None:
            pass
        else:
            dt_date = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=event[key] / 1000)
            dt_str = str(dt_date.strftime(format_str))
        return dt_str

    def sub_el(self, parent, name, text=None, **kwargs):
        el = ET.SubElement(parent, name, **kwargs)
        if text:
            el.text = text
        return el

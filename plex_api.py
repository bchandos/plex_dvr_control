import requests
import xml.etree.ElementTree as ET

from urllib import parse


class PlexServer:
    def __init__(self, host, token, client_identifier, port='32400'):
        self.library = _PlexLibrary(host=host, token=token, port=port)
        self.dvr = _PlexDVR(host=host,
                            token=token,
                            client_identifier=client_identifier,
                            port=port)


class _PlexLibrary:

    def __init__(self, host, token, port='32400'):
        self.base_url = f'http://{host}:{port}'
        # self.dvr_base_url = self.base_url + '/tv.plex.providers.epg.onconnect:2'
        self.parameters = {'X-Plex-Token': token}
        self.token = token

    def shows(self, library_id, search_title=None):
        """
        Using the library ID, returns all shows available. Takes optional search string.
        :param library_id: the Plex library ID
        :returns: all show attributes from a library
        :rtype: list
        """
        if search_title:
            p = self.parameters
            p['title'] = search_title
        else:
            p = self.parameters
        all_shows = list()
        r = requests.get(
            f'{self.base_url}/library/sections/{str(library_id)}/all', params=p)
        shows_root = ET.fromstring(r.text)
        for show in shows_root:
            if 'type' in show.attrib and show.attrib['type'] == 'show':
                d = show.attrib
                d['direct_url'] = f'{self.base_url}{show.attrib["key"]}/'
                all_shows.append(d)
        return all_shows

    def seasons(self, show_key=None, show_url=None):
        """
        Using the Plex key for the show or a direct url, find all seasons 
        in library and return all available attributes for the show's 
        seasons, plus a direct url to return all episodes from each season.
        :param show_key: the Plex ID of the show
        :param show_url: the direct URL to the show
        :returns: all season attributes and direct url
        :rtype: list
        """
        show_seasons = list()
        if show_url:
            r = requests.get(show_url, params=self.parameters)
        elif show_key:
            r = requests.get(
                f'{self.base_url}/library/metadata/{str(show_key)}/children/', params=self.parameters)
        else:
            raise ValueError(
                'If not providing show_url, must provide show_key.')
        seasons_root = ET.fromstring(r.text)
        for season in seasons_root:
            if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
                d = season.attrib
                d['direct_url'] = f'{self.base_url}{season.attrib["key"]}/'
                show_seasons.append(d)
        return show_seasons

    def episodes(self, show_key=None, season=None, season_url=None):
        """
        Using the show key and season number (or a direct url, as returned by ``get_seasons``),
        return attributes of all episodes from a season, plus a direct url to return
        episode attributes.
        :param show_key: the Plex ID of the show
        :param season: the season number
        :param season_url: the direct url to the season
        :returns: all episode attributes and direct url
        :rtype: list
        """
        episodes = list()
        if season_url:
            r = requests.get(season_url, params=self.parameters)
        elif show_key and season:
            show_key = str(show_key)
            season = str(season)
            seasons = self.seasons(show_key)
            season_keys = {x['index']: x['direct_url'] for x in seasons}
            if season not in season_keys:
                return None
            r = requests.get(season_keys[season], params=self.parameters)
        else:
            raise ValueError(
                'If not providing season_url, provide both show_key and season.')
        episodes_root = ET.fromstring(r.text)
        for episode in episodes_root:
            d = episode.attrib
            d['direct_url'] = f'{self.base_url}{episode.attrib["key"]}/'
            episodes.append(d)
        return episodes

    def episode(self, show_key=None, season=None, episode=None, episode_url=None):
        """
        Using the show_key, season and episode numbers (or a direct url as returned
        by ``get_episodes``) return attributes of a particular episode.
        :param show_key: the Plex ID of the show
        :param season: the season number
        :param episode: the epsidoe number
        :param episode_url: the direct url to the episode
        :return: single episode attributes
        :rtype: dict
        """
        if episode_url:
            r = requests.get(episode_url, params=self.parameters)
        elif show_key and season and episode:
            show_key = str(show_key)
            season = str(season)
            episode = str(episode)
            episodes = self.episodes(show_key=show_key, season=season)
            episode_keys = {x['index']: x['direct_url'] for x in episodes}
            if episode not in episode_keys:
                return None
            r = requests.get(episode_keys[episode], params=self.parameters)
        else:
            raise ValueError(
                'If not providing season_url, provide show_key, season, and episode.')
        episode_root = ET.fromstring(r.text)
        d = dict()
        for container in episode_root:
            d['container'] = container.attrib
            for media in container:
                d['media'] = media.attrib
                for video in media:
                    try:
                        d['video'].append(video.attrib)
                    except KeyError:
                        d['video'] = list()
                        d['video'].append(video.attrib)
        return d


class _PlexDVR:

    def __init__(self, host, token, client_identifier, port='32400'):
        self.base_url = f'http://{host}:{port}'
        self.dvr_base_url = self.base_url + '/tv.plex.providers.epg.onconnect:2'
        self.parameters = {'X-Plex-Token': token}
        self.token = token
        self.client_identifier = client_identifier

    def subscriptions(self):
        r = requests.get(
            f'{self.base_url}/media/subscriptions', params=self.parameters)
        sub_tree = ET.fromstring(r.text)
        sub_list = list()
        for sub in sub_tree:
            for directory in sub:
                sub_list.append(sub.attrib + directory.attrib)
        return sub_list

    def shows(self, search_title=None):
        # /tv.plex.providers.epg.onconnect:2/sections/2/all
        if search_title:
            p = self.parameters
            p['title'] = search_title
        else:
            p = self.parameters
        r = requests.get(
            f'{self.dvr_base_url}/sections/2/all', params=p)
        show_tree = ET.fromstring(r.text)
        show_list = list()
        for show in show_tree:
            show_list.append(show.attrib)
        return show_list

    def seasons(self, show_gracenote_id=None, show_url=None):
        if show_url:
            r = requests.get(show_url)
        elif show_gracenote_id:
            show_encoded_url = parse.quote(
                f'com.gracenote.onconnect://show/{show_gracenote_id}', safe='').replace('.', '%2E')
            r = requests.get(
                f'{self.dvr_base_url}/metadata/{show_encoded_url}/children')
        else:
            raise ValueError(
                'If not providing show URL, must provide Gracenote ID.')
        seasons_root = ET.fromstring(r.text)
        guide_show_seasons = list()
        for season in seasons_root:
            if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
                d = season.attrib
                d['direct_url'] = f'{self.base_url}{season.attrib["key"]}/'
                d['show_year'] = seasons_root.attrib['parentYear']
                guide_show_seasons.append(d)
        return guide_show_seasons

    def episodes(self, show_gracenote_id=None, season=None, season_url=None):
        # com.gracenote.onconnect://season/{show_gracenote_id}/{season}
        # /tv.plex.providers.epg.onconnect:2/metadata/com%2Egracenote%2Eonconnect%3A%2F%2Fseason%2F184483%2F6/children
        if season_url:
            r = requests.get(season_url)
        elif show_gracenote_id and season:
            season_encoded_url = parse.quote(
                f'com.gracenote.onconnect://season/{show_gracenote_id}/{season}', safe='').replace('.', '%2E')
            r = requests.get(
                f'{self.dvr_base_url}/metadata/{season_encoded_url}/children')
        else:
            raise ValueError(
                'If not providing season URL, must provide Gracenote ID and season.')
        episodes_root = ET.fromstring(r.text)
        guide_season_episodes = list()
        for episode in episodes_root:
            if 'type' in episode.attrib.keys() and episode.attrib['type'] == 'episode':
                d = episode.attrib
                d['direct_url'] = f'{self.base_url}{season.attrib["key"]}/'
                d['media'] = list()
                for media in episode:
                    d['media'].append(media.attrib)
                guide_season_episodes.append(d)
        return guide_season_episodes

    def episode(self, show_gracenote_id=None, season=None, episode=None, episode_gracenote_id=None, episode_url=None):
        # com.gracenote.onconnect://episode/EP############
        # /tv.plex.providers.epg.onconnect:2/metadata/com%2Egracenote%2Eonconnect%3A%2F%2Fepisode%2FEP002960010113
        # not sure this is necessary as most, if not all, data is available in the season listing page
        if show_gracenote_id and season and episode:
            season_episodes = self.episodes(
                show_gracenote_id=show_gracenote_id, season=season)
            for ep in season_episodes:
                if ep['index'] == str(episode):
                    return ep
        elif episode_gracenote_id:
            pass
        elif episode_url:
            pass
        else:
            raise ValueError(
                'Provide either: show id, season, and episode *or* episode id *or* episode url.')

    def set_recording(self, episode, year):
        """
        Prepares and sends the Plex POST request to add a recording to the Plex DVR.
        :param episode: The episode object representing the guide XML data for an episode
        :param year: the year the show began; only available in the root element of a season
        :returns: True if succesful, False if failed
        :rtype: bool
        """

        parameters_prefs = {
            'prefs[minVideoQuality]': '0',
            'prefs[replaceLowerQuality]': 'false',
            'prefs[recordPartials]': 'false',
            'prefs[startOffsetMinutes]': '0',
            'prefs[endOffsetMinutes]': '0',
            'prefs[lineupChannel]': '',
            'prefs[startTimeslot]': '-1',
            'prefs[comskipEnabled]': '1',
            'prefs[oneShot]': 'true',
            'targetLibrarySectionID': '3',
            'targetSectionLocationID': '',
            'includeGrabs': '1'}
        parameters_brackets = {
            'hints[grandparentGuid]': episode['grandparentGuid'],
            'hints[grandparentThumb]': episode['grandparentThumb'],
            'hints[grandparentTitle]': episode['grandparentTitle'],
            'hints[grandparentYear]': year,
            'hints[guid]': episode['guid'],
            'hints[index]': episode['index'],
            'hints[originallyAvailableAt]': episode['originallyAvailableAt'][:10],
            'hints[parentIndex]': episode['parentIndex'],
            'hints[title]': episode['title'],
            'hints[type]': '4',
            'hints[year]': episode['year'],
            'params[airingChannels]': parse.quote(episode[0]['channelIdentifier']+'='+episode[0]['channelTitle']),
            'params[airingTimes]': int(
                ((int(episode['originallyAvailableAt'][11:13]) + 8) +
                 int(episode['originallyAvailableAt'][14:16]) / 60) * 60) % 1440,
            'params[libraryType]': '2',
            'params[mediaProviderID]': '3',
            'type': '4',
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '3.77.4',
            'X-Plex-Client-Identifier': self.client_identifier,
            'X-Plex-Platform': 'Chrome',
            'X-Plex-Platform-Version': '67.0',
            'X-Plex-Sync-Version': '2',
            'X-Plex-Device': 'Windows',
            'X-Plex-Device-Name': 'Chrome',
            'X-Plex-Device-Screen-Resolution': '1920x1080',
            'X-Plex-Token': self.token,
            'X-Plex-Language': 'en'
        }

        parameters = f'{parse.urlencode(parameters_prefs, quote_via=parse.quote)}&' \
            f'{parse.urlencode(parameters_brackets, safe="[]", quote_via=parse.quote)}'

        url = f'{self.base_url}/media/subscriptions?{parameters}'
        p = requests.post(url)
        return p.ok

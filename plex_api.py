import requests
import xml.etree.ElementTree as ET


class PlexServer:
    def __init__(self, host, token, port='32400'):
        self.base_url = f'http://{host}:{port}'
        self.parameters = {'X-Plex-Token': token}
        self.library = PlexLibrary(host=host, token=token, port=port)
        self.dvr = PlexDVR(host=host, token=token, port=port)


class PlexLibrary(PlexServer):

    def all_shows(self, library_id):
        """
        Using the library ID, returns all shows available.
        :param library_id: the Plex library ID
        :returns: all show attributes from a library
        :rtype: list
        """
        all_shows = list()
        r = requests.get(
            f'{self.base_url}/library/sections/{str(library_id)}/all', params=self.parameters)
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


class PlexDVR(PlexServer):

    def subscriptions(self):
        pass

    def shows(self, show_gracenote_id):
        pass

    def seasons(self, show_gracenote_id=None, show_url=None):
        pass

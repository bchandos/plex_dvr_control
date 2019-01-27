import requests
import xml.etree.ElementTree as ET


class PlexServer:
    def __init__(self, host, token, port='32400'):
        self.base_url = f'http://{host}:{port}'
        self.parameters = {'X-Plex-Token': token}

    def get_seasons(self, show_key):
        show_seasons = dict()
        r = requests.get(
            f'{self.base_url}/library/metadata/{show_key}/children/', params=self.parameters)
        seasons_root = ET.fromstring(r.text)
        for season in seasons_root:
            # does try-except block work better?
            if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
                s = season.attrib['index']
                show_seasons[s] = f'{self.base_url}{season.attrib["key"]}/'
        return show_seasons

    def get_episodes(self, show_id, season, season_url=None):
        episodes = dict()
        if season_url:
            r = requests.get(season_url, params=self.parameters)
        else:
            seasons = self.get_seasons(show_id)
            if season not in seasons.keys():
                return None
            r = requests.get(seasons[season], params=self.parameters)
        episodes_root = ET.fromstring(r.text)
        for episode in episodes_root:
            e = episode.attrib['index']
            episodes[e] = f'{self.base_url}{episode.attrib["key"]}/'
        return episodes

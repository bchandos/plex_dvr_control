import requests
import xml.etree.ElementTree as ET
import sqlite3
from difflib import SequenceMatcher
from urllib import parse
import settings
import logging
import os

HOST_NAME = settings.server_settings['host']
PORT = settings.server_settings['port']
BASE_URL = f'http://{HOST_NAME}:{PORT}'
PLEX_TOKEN = settings.server_settings['plex_token']

script_dir = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger('plex-dvr-control')
logger.setLevel(logging.INFO)
fh = logging.FileHandler(f'{script_dir}/plex_dvr_control.log')
ch = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)


def update_db_from_plex():
    """
    Searches the Plex library for episodes of all shows from shows table in DB and add each episode
    to the episode table in DB. episode_plex_key is unique so it will ignore episodes already in the table.
    Then scans episodes table for episodes no longer in the library and deletes them.
    :return: None
    """
    # updates the database with latest Plex library information

    parameters = {'X-Plex-Token': PLEX_TOKEN}
    conn = sqlite3.connect(f'{script_dir}/tv_shows.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    all_shows = []
    for show in cursor.execute('SELECT plex_key, id FROM shows'):
        r = requests.get(
            f'{BASE_URL}/library/metadata/{show["plex_key"]}/children/', params=parameters)
        seasons_root = ET.fromstring(r.text)
        for season in seasons_root:
            if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
                key = season.attrib['key']
                r = requests.get(f'{BASE_URL}{key}/', params=parameters)
                episodes_root = ET.fromstring(r.text)
                for episode in episodes_root:
                    all_shows.append((show['id'],
                                      int(season.attrib['index']),
                                      int(episode.attrib['index']),
                                      episode.attrib['title'],
                                      int(season.attrib['ratingKey']),
                                      int(episode.attrib['ratingKey'])))
    cursor = conn.executemany('''INSERT or IGNORE INTO 
                                episodes(show_id, season, episode, name, season_plex_key, episode_plex_key) 
                                VALUES (?,?,?,?,?,?)''', all_shows)
    conn.commit()
    db = list(conn.execute('SELECT episode_plex_key FROM episodes'))
    db_episodes = [x['episode_plex_key'] for x in db]
    plex_episodes = [x[5] for x in all_shows]
    db_removals = list(set(db_episodes) - set(plex_episodes))
    q = [(x,) for x in db_removals]
    if len(db_removals) > 0:
        cursor.executemany(
            'DELETE FROM episodes WHERE episode_plex_key=(?)', q)
        conn.commit()


def check_guide_for_missing_episodes():
    """
    Searches the Plex guide for episodes of shows from shows table in DB. Checks season, episode, and title
    against existing shows in episodes table in DB. If not found in DB, and not already on the recording schedule,
    will send the POST request to Plex to add the recording.
    :return: None
    """

    parameters = {'X-Plex-Token': PLEX_TOKEN}
    r = requests.get(f'{BASE_URL}/media/subscriptions', params=parameters)
    subscriptions_root = ET.fromstring(r.text)
    guids = list()
    for sub in subscriptions_root.iter('Video'):
        guids.append(sub.attrib['guid'])
    conn = sqlite3.connect(f'{script_dir}/tv_shows.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    shows = list(cursor.execute('SELECT gracenote_id, id FROM shows'))
    for show in shows:
        episodes_in_db = list(cursor.execute('SELECT season, episode, name, episode_gracenote_id, id FROM episodes '
                                             'WHERE show_id=(?)', (show['id'],)))
        show_encoded_url = parse.quote(
            f'com.gracenote.onconnect://show/{show["gracenote_id"]}', safe='')
        r = requests.get(f'{BASE_URL}/tv.plex.providers.epg.onconnect:2'
                         f'/metadata/{show_encoded_url}/children/',
                         params=parameters)
        seasons_root = ET.fromstring(r.text)
        for season in seasons_root:
            if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
                key = season.attrib['key']
                r = requests.get(f'{BASE_URL}{key}/', params=parameters)
                episodes_root = ET.fromstring(r.text)
                for episode in episodes_root:
                    in_db = False
                    for d in episodes_in_db:
                        if episode.attrib['guid'][-12:] == str(d['episode_gracenote_id']).zfill(12):
                            in_db = True
                        elif SequenceMatcher(None, str(d['name']), str(episode.attrib['title'])).ratio() > 0.90:
                            in_db = True
                        elif d['season'] == int(episode.attrib['parentIndex']) \
                                and d['episode'] == int(episode.attrib['index']) \
                                and SequenceMatcher(None, d['name'], episode.attrib['title']).ratio() > 0.70:
                            in_db = True
                    if not in_db and episode.attrib['guid'] not in guids:
                        set_recording(
                            episode, seasons_root.attrib['parentYear'])
                    if in_db:
                        if not d['episode_gracenote_id']:
                            cursor.execute('UPDATE episodes SET episode_gracenote_id=(?) WHERE id=(?)', (int(
                                episode.attrib['guid'][-12:]), d['id']))
                            conn.commit()
                            logger.info('Updated gracenote id.')
                        logger.info(f'Skipped {episode.attrib["title"]}, {episode.attrib["grandparentTitle"]}'
                                    f' {episode.attrib["parentIndex"]}x{episode.attrib["index"]} - already in library')

                    if episode.attrib['guid'] in guids:
                        logger.info(f'Skipped {episode.attrib["title"]}, {episode.attrib["grandparentTitle"]}'
                                    f' {episode.attrib["parentIndex"]}x{episode.attrib["index"]} - already scheduled')


def set_recording(episode_elem, year):
    """
    Prepares and send the Plex POST request to add a recording to the Plex DVR.
    :param episode_elem: The Element object representing the guide XML data for an episode
    :param year: the year the show began; only available in the root element of a season
    :return: None
    """

    base_url = f'{BASE_URL}/media/subscriptions'
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
        'hints[grandparentGuid]': episode_elem.attrib['grandparentGuid'],
        'hints[grandparentThumb]': episode_elem.attrib['grandparentThumb'],
        'hints[grandparentTitle]': episode_elem.attrib['grandparentTitle'],
        'hints[grandparentYear]': year,
        'hints[guid]': episode_elem.attrib['guid'],
        'hints[index]': episode_elem.attrib['index'],
        'hints[originallyAvailableAt]': episode_elem.attrib['originallyAvailableAt'][:10],
        'hints[parentIndex]': episode_elem.attrib['parentIndex'],
        'hints[title]': episode_elem.attrib['title'],
        'hints[type]': '4',
        'hints[year]': episode_elem.attrib['year'],
        'params[airingChannels]': parse.quote(episode_elem[0].attrib['channelIdentifier']+'='+episode_elem[0].attrib['channelTitle']),
        'params[airingTimes]': int(
            ((int(episode_elem.attrib['originallyAvailableAt'][11:13]) + 8) +
             int(episode_elem.attrib['originallyAvailableAt'][14:16]) / 60) * 60) % 1440,
        'params[libraryType]': '2',
        'params[mediaProviderID]': '3',
        'type': '4',
        'X-Plex-Product': 'Plex Web',
        'X-Plex-Version': '3.59.1',
        'X-Plex-Client-Identifier': settings.server_settings['client_identifier'],
        'X-Plex-Platform': 'Chrome',
        'X-Plex-Platform-Version': '67.0',
        'X-Plex-Sync-Version': '2',
        'X-Plex-Device': 'Windows',
        'X-Plex-Device-Name': 'Chrome',
        'X-Plex-Device-Screen-Resolution': '1920x1080',
        'X-Plex-Token': PLEX_TOKEN,
        'X-Plex-Language': 'en'
    }

    parameters = f'{parse.urlencode(parameters_prefs, quote_via=parse.quote)}&' \
                 f'{parse.urlencode(parameters_brackets, safe="[]", quote_via=parse.quote)}'

    url = f'{base_url}?{parameters}'
    p = requests.post(url)
    if p.ok:
        logger.info(f'Added recording: {episode_elem.attrib["grandparentTitle"]} - '
                    f'{episode_elem.attrib["parentIndex"]}x{episode_elem.attrib["index"]} - '
                    f'{episode_elem.attrib["title"]}')
    else:
        logger.info(f'Plex post request failed: {p.status_code}.')


def main():
    update_db_from_plex()
    check_guide_for_missing_episodes()


if __name__ == "__main__":
    main()

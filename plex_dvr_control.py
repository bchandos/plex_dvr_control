import requests
import xml.etree.ElementTree as ET
import sqlite3
from difflib import SequenceMatcher
from urllib import parse
# import settings
from json_settings import JSONSettings
import logging
import os
import argparse

from plex_api import PlexServer

# TODO: convert settings.py to another safe format

settings = JSONSettings('settings.json')

HOST_NAME = settings.get_setting('server_settings', 'host')
PORT = settings.get_setting('server_settings', 'port')
BASE_URL = f'http://{HOST_NAME}:{PORT}'
PLEX_TOKEN = settings.get_setting('server_settings', 'plex_token')
CLIENT_ID = settings.get_setting('server_settings', 'client_identifier')

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

Plex = PlexServer(host=HOST_NAME, token=PLEX_TOKEN,
                  client_identifier=CLIENT_ID)


def main():
    parser = argparse.ArgumentParser(
        description='Utility to find missing episodes in Plex DVR and set recording.')
    parser.add_argument('--search', nargs=2,
                        help='Search by Plex ID and Gracenote ID and add missing episodes to Plex DVR.',
                        metavar=('PLEX-ID', 'GRACENOTE-ID'))
    parser.add_argument('--show_title_search', nargs=1,
                        help='Attempt to retrieve plex key and gracenote id by show title.',
                        metavar='TITLE')
    parser.add_argument('--force_match', nargs=2,
                        help='Manually match an episode key with a gracenote id and store.',
                        metavar=('PLEX-KEY', 'GRACENOTE-KEY'))
    parser.add_argument('--force_unmatch', nargs=2,
                        help='Manually unmatch an episode key with a gracenote id and store.',
                        metavar=('PLEX-KEY', 'GRACENOTE-KEY'))
    subparsers = parser.add_subparsers(help='sub-command help')
    parser_settings = subparsers.add_parser('settings', help='settings help')
    parser_settings.add_argument(
        '--set_all', nargs=4, help='Set all server settings at once.',
        metavar=('HOST', 'PORT', 'PLEX-TOKEN', 'CLIENT-ID'))
    parser_settings.add_argument(
        '--set_host', nargs=1, help='Set the host in the settings file.', metavar='HOST')
    parser_settings.add_argument(
        '--set_port', nargs=1, help='Set the port in the settings file.', metavar='PORT')
    parser_settings.add_argument(
        '--set_token', nargs=1, help='Set the Plex token in the settings file.', metavar='PLEX-TOKEN')
    parser_settings.add_argument(
        '--set_client_id', nargs=1, help='Set the client identifier string in the settings file.', metavar='CLIENT-ID')

    args = parser.parse_args()
    if args.search:
        search(args.search[0], args.search[1])
    elif args.show_title_search:
        search_plex_by_title(args.show_title_search[0])
    elif args.force_match:
        plex_id = args.force_match[0]
        gracenote_id = args.force_match[1]
        settings.add_setting('force_matches', plex_id, gracenote_id)
    elif args.force_unmatch:
        plex_id = args.force_unmatch[0]
        gracenote_id = args.force_unmatch[1]
        settings.add_setting('force_unmatches', plex_id, gracenote_id)
    elif args.set_all:
        key_order = ['host', 'port', 'plex_token', 'client_identifier']
        for arg, k in zip(args.set_all, key_order):
            settings.add_setting('server_settings', k, arg)
    elif args.set_host or args.set_port or args.set_token or args.set_client_id:
        if args.set_host:
            settings.add_setting('server_settings', 'host', args.set_host[0])
        if args.set_port:
            settings.add_setting('server_settings', 'port', args.set_port[0])
        if args.set_token:
            settings.add_setting(
                'server_settings', 'plex_token', args.set_token[0])
        if args.set_cliend_id:
            settings.add_setting(
                'server_settings', 'client_identifier', args.set_client_id[0])


def search(plex_key, gracenote_id):
    plib_seasons = Plex.library.seasons(show_key=plex_key)
    dvr_seasons = Plex.dvr.seasons(gracenote_id)
    plib_episodes = list()
    dvr_episodes = list()
    for s in plib_seasons:
        plib_episodes.append(Plex.library.episodes(season_url=s['direct_url']))
    for s in dvr_seasons:
        dvr_episodes.append(Plex.dvr.episodes(season_url=s['direct_url']))
    for dvr_ep in dvr_episodes:
        for lib_ep in plib_episodes:
            in_library = False
            dvr_ep_str = f'{dvr_ep["title"]} (S{dvr_ep["parentIndex"]}E{dvr_ep["index"]}, Gracenote ID: {gracenote_episode_id(dvr_ep["ratingKey"])})'
            if SequenceMatcher(None, dvr_ep['title'], lib_ep['title']).ratio() > 0.90:
                in_library = True
                lib_ep_str = f'{lib_ep["title"]} (S{lib_ep["parentIndex"]}E{lib_ep["index"]}, Plex ID: {lib_ep["ratingKey"]})'
                break
            elif dvr_ep['parentIndex'] == int(lib_ep['parentIndex']) \
                    and dvr_ep['index'] == int(lib_ep['index']) \
                    and SequenceMatcher(None, dvr_ep['title'], lib_ep['title']).ratio() > 0.70:
                in_library = True
                lib_ep_str = f'{lib_ep["title"]} (S{lib_ep["parentIndex"]}E{lib_ep["index"]}, Plex ID: {lib_ep["ratingKey"]})'
                break
        if in_library:
            logger.info(
                f'Guide episode {dvr_ep_str} matched with library episode {lib_ep_str}. Use --force-unmatch to correct matching errors.')
        elif dvr_ep['guid'] in Plex.dvr.current_recordings():
            logger.info(
                f'Guide episode {dvr_ep_str} already in recording schedule. Skipping.')
        else:
            Plex.dvr.set_recording(dvr_ep, dvr_seasons[0]['show_year'])
            logger.info(
                f'Guide episode {dvr_ep_str} not found in library, added recording. Use --force-match to correct missing matches.')


def gracenote_episode_id(key):
    return key.split('%2F')[-1]


def search_plex_by_title(show_title):
    """
    Search both the Plex television library and DVR guide listings for a show,
    by title, and return their respective keys, if found. Uses Plex native search.

    :param show_title: the show title to search for
    :type show_title: str
    :returns: matches in Plex library and guide listings, if available
    :rtype: str
    """
    if type(show_title) is str:
        # don't hit the API if show_title is not valid
        library_shows = Plex.library.shows(
            library_id=3, search_title=show_title)
        guide_shows = Plex.dvr.shows(search_title=show_title)
        print('Library Listings')
        for sh in library_shows:
            print('\t%s - %s' % (sh['title'], sh['ratingKey']))
        print('DVR Guide Listings')
        for sh in guide_shows:
            print('\t%s - %s' % (sh['title'], sh['guid'].split('/')[-1:][0]))


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
        'X-Plex-Version': '3.77.4',
        'X-Plex-Client-Identifier': CLIENT_ID,
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
# def update_db_from_plex():
#     """
#     Searches the Plex library for episodes of all shows from shows table in DB and add each episode
#     to the episode table in DB. episode_plex_key is unique so it will ignore episodes already in the table.
#     Then scans episodes table for episodes no longer in the library and deletes them.
#     :return: None
#     """
#     # updates the database with latest Plex library information

#     parameters = {'X-Plex-Token': PLEX_TOKEN}
#     conn = sqlite3.connect(f'{script_dir}/tv_shows.db')
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
#     all_shows = []
#     for show in cursor.execute('SELECT plex_key, id FROM shows'):
#         r = requests.get(
#             f'{BASE_URL}/library/metadata/{show["plex_key"]}/children/', params=parameters)
#         seasons_root = ET.fromstring(r.text)
#         for season in seasons_root:
#             if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
#                 key = season.attrib['key']
#                 r = requests.get(f'{BASE_URL}{key}/', params=parameters)
#                 episodes_root = ET.fromstring(r.text)
#                 for episode in episodes_root:
#                     all_shows.append((show['id'],
#                                       int(season.attrib['index']),
#                                       int(episode.attrib['index']),
#                                       episode.attrib['title'],
#                                       int(season.attrib['ratingKey']),
#                                       int(episode.attrib['ratingKey'])))
#     cursor = conn.executemany('''INSERT or IGNORE INTO
#                                 episodes(show_id, season, episode, name, season_plex_key, episode_plex_key)
#                                 VALUES (?,?,?,?,?,?)''', all_shows)
#     conn.commit()
#     db = list(conn.execute('SELECT episode_plex_key FROM episodes'))
#     db_episodes = [x['episode_plex_key'] for x in db]
#     plex_episodes = [x[5] for x in all_shows]
#     db_removals = list(set(db_episodes) - set(plex_episodes))
#     q = [(x,) for x in db_removals]
#     if len(db_removals) > 0:
#         cursor.executemany(
#             'DELETE FROM episodes WHERE episode_plex_key=(?)', q)
#         conn.commit()


# def check_guide_for_missing_episodes():
#     """
#     Searches the Plex guide for episodes of shows from shows table in DB. Checks season, episode, and title
#     against existing shows in episodes table in DB. If not found in DB, and not already on the recording schedule,
#     will send the POST request to Plex to add the recording.
#     :return: None
#     """

#     parameters = {'X-Plex-Token': PLEX_TOKEN}
#     r = requests.get(f'{BASE_URL}/media/subscriptions', params=parameters)
#     subscriptions_root = ET.fromstring(r.text)
#     guids = list()
#     for sub in subscriptions_root.iter('Video'):
#         guids.append(sub.attrib['guid'])
#     conn = sqlite3.connect(f'{script_dir}/tv_shows.db')
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
#     shows = list(cursor.execute('SELECT gracenote_id, id FROM shows'))
#     for show in shows:
#         episodes_in_db = list(cursor.execute('SELECT season, episode, name, episode_gracenote_id, id FROM episodes '
#                                              'WHERE show_id=(?)', (show['id'],)))
#         show_encoded_url = parse.quote(
#             f'com.gracenote.onconnect://show/{show["gracenote_id"]}', safe='')
#         r = requests.get(f'{BASE_URL}/tv.plex.providers.epg.onconnect:2'
#                          f'/metadata/{show_encoded_url}/children/',
#                          params=parameters)
#         seasons_root = ET.fromstring(r.text)
#         for season in seasons_root:
#             if 'type' in season.attrib.keys() and season.attrib['type'] == 'season':
#                 key = season.attrib['key']
#                 r = requests.get(f'{BASE_URL}{key}/', params=parameters)
#                 episodes_root = ET.fromstring(r.text)
#                 for episode in episodes_root:
#                     in_db = False
#                     for d in episodes_in_db:
#                         if episode.attrib['guid'][-12:] == str(d['episode_gracenote_id']).zfill(12):
#                             in_db = True
#                         elif SequenceMatcher(None, str(d['name']), str(episode.attrib['title'])).ratio() > 0.90:
#                             in_db = True
#                         elif d['season'] == int(episode.attrib['parentIndex']) \
#                                 and d['episode'] == int(episode.attrib['index']) \
#                                 and SequenceMatcher(None, d['name'], episode.attrib['title']).ratio() > 0.70:
#                             in_db = True
#                     if not in_db and episode.attrib['guid'] not in guids:
#                         set_recording(
#                             episode, seasons_root.attrib['parentYear'])
#                     if in_db:
#                         if not d['episode_gracenote_id']:
#                             cursor.execute('UPDATE episodes SET episode_gracenote_id=(?) WHERE id=(?)', (int(
#                                 episode.attrib['guid'][-12:]), d['id']))
#                             conn.commit()
#                             logger.info('Updated gracenote id.')
#                         logger.info(f'Skipped {episode.attrib["title"]}, {episode.attrib["grandparentTitle"]}'
#                                     f' {episode.attrib["parentIndex"]}x{episode.attrib["index"]} - already in library')

#                     if episode.attrib['guid'] in guids:
#                         logger.info(f'Skipped {episode.attrib["title"]}, {episode.attrib["grandparentTitle"]}'
#                                     f' {episode.attrib["parentIndex"]}x{episode.attrib["index"]} - already scheduled')


if __name__ == "__main__":
    main()

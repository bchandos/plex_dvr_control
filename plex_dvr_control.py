import requests
import xml.etree.ElementTree as ET
import sqlite3
from difflib import SequenceMatcher
from urllib import parse
from json_settings import JSONSettings
import logging
import os
import argparse

from plex_api import PlexServer

settings = JSONSettings('settings.json')

HOST_NAME = settings.get_setting('server_settings', 'host')
PORT = settings.get_setting('server_settings', 'port')
BASE_URL = f'http://{HOST_NAME}:{PORT}'
PLEX_TOKEN = settings.get_setting('server_settings', 'plex_token')
CLIENT_ID = settings.get_setting('server_settings', 'client_identifier')


logger = logging.getLogger('plex-dvr-control')
logger.setLevel(logging.INFO)
fh = logging.FileHandler('plex_dvr_control.log')
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

    if getattr(args, 'set_all', False):
        if args.set_all:
            key_order = ['host', 'port', 'plex_token', 'client_identifier']
            for arg, k in zip(args.set_all, key_order):
                settings.add_setting('server_settings', k, arg)
        elif args.set_host or args.set_port or args.set_token or args.set_client_id:
            if args.set_host:
                settings.add_setting(
                    'server_settings', 'host', args.set_host[0])
            if args.set_port:
                settings.add_setting(
                    'server_settings', 'port', args.set_port[0])
            if args.set_token:
                settings.add_setting(
                    'server_settings', 'plex_token', args.set_token[0])
            if args.set_cliend_id:
                settings.add_setting(
                    'server_settings', 'client_identifier', args.set_client_id[0])
        else:
            parser_settings.print_help()

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
    else:
        parser.print_help()


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
        print('----------------')
        for sh in library_shows:
            print('\t%s - %s' % (sh['title'], sh['ratingKey']))
        if not library_shows:
            print('\tNo results.')
        print('\n')
        print('DVR Guide Listings')
        print('------------------')
        for sh in guide_shows:
            print('\t%s - %s' % (sh['title'], sh['guid'].split('/')[-1:][0]))
        if not guide_shows:
            print('\tNo results.')
        print('\n')


if __name__ == "__main__":
    main()

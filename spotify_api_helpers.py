import base64
import datetime
import time
import uuid
from datetime import timedelta

import requests
from requests import Request
from tinydb import TinyDB, Query

import rss_feed_generator
import params_utils

db_root_users = TinyDB('data/database_users.json')
db_users = db_root_users.table('users', cache_size=0)
db_root_artists = TinyDB('data/database_artists.json')
db_artists = db_root_artists.table('artists', cache_size=0)
db_root_releases = TinyDB('data/database_releases.json')
db_releases = db_root_releases.table('releases', cache_size=0)
db_root_metadata = TinyDB('data/database_metadata.json')
db_metadata = db_root_metadata.table('metadata', cache_size=0)
db_root_shows = TinyDB('data/database_shows.json')
db_shows = db_root_shows.table('shows', cache_size=0)
db_root_episodes = TinyDB('data/database_episodes.json')
db_episodes = db_root_episodes.table('episodes', cache_size=0)

params = params_utils.ConfigManager()
client_id = params.get('client_id')
client_secret = params.get('client_secret')
authorization = f'Basic {base64.b64encode((f"{client_id}:{client_secret}").encode("ascii")).decode("ascii")}'

logging = params.get_logger()


def get_authorization_code_url():
    scope = 'user-follow-read,user-read-playback-position,user-library-read'
    state = uuid.uuid4()

    request_params = {
        'response_type': 'code',
        'client_id': client_id,
        'scope': scope,
        'redirect_uri': f'{params.get("application_url")}/auth',
        'state': state
    }

    return Request(url='https://accounts.spotify.com/authorize?', params=request_params).prepare().url


def get_user_stored_token(refresh=True):
    try:
        found = db_users.all()[0]
    except:
        logging.error(
            f'Unable to retrieve user in database, please connect you spotify account here : {params.get("application_url")}/login')
        return None

    if found is None:
        logging.error(f'No user found, please connect you spotify account here : {params.get("application_url")}/login')
        return None
    else:
        current_date = datetime.datetime.now()

        if found.get('expires_on') < current_date.timestamp() and refresh is True:
            logging.info(f'Stored user access_token expired on { datetime.datetime.fromtimestamp(found.get("expires_on")) }, requesting a new one')
            refresh_access_token()
            return get_user_stored_token()

        return found


def request_access_token(code):
    auth_query = requests.post(url='https://accounts.spotify.com/api/token',
                               headers={
                                   'Content-Type': 'application/x-www-form-urlencoded',
                                   'Authorization': authorization
                               },
                               data={
                                   'code': code,
                                   'redirect_uri': f'{params.get("application_url")}/auth',
                                   'grant_type': 'authorization_code'
                               }
                               )

    if auth_query.status_code == 200:
        current_date = datetime.datetime.now()
        db_root_users.drop_table('users')

        user_object = auth_query.json()
        expires_on = current_date + timedelta(seconds=user_object.get('expires_in'))
        user_object['expires_on'] = expires_on.timestamp()

        logging.info(f'New token expires on {expires_on}')
        db_users.insert(user_object)

    elif auth_query.status_code in [400,429]:
        raise PermissionError(f'{auth_query.status_code} - {auth_query.text}')
    else:
        logging.error(f'access_token request query failed - {auth_query.status_code} - {auth_query.text}')

    return auth_query


def refresh_access_token():
    stored_user_token = get_user_stored_token(refresh=False)

    refresh_query = requests.post(url='https://accounts.spotify.com/api/token',
                                  headers={
                                      'Content-Type': 'application/x-www-form-urlencoded',
                                      'Authorization': authorization
                                  },
                                  data={
                                      'grant_type': 'refresh_token',
                                      'refresh_token': stored_user_token.get('refresh_token')
                                  }
                                  )

    if refresh_query.status_code == 200:
        current_date = datetime.datetime.now()

        user_object = refresh_query.json()
        expires_on = current_date + timedelta(seconds=user_object.get('expires_in'))
        user_object['expires_on'] = expires_on.timestamp()

        logging.info(f'New token expires on {expires_on}')
        db_users.update(user_object, doc_ids=[1])

    elif refresh_query.status_code in [400,429]:
        raise PermissionError(f'{refresh_query.status_code} - {refresh_query.text}')
    else:
        logging.error(f'access_token refresh query failed - {refresh_query.status_code} - {refresh_query.text}')

    return refresh_query


def get_user_followed(url=None, followed=[], retry_count=0, type='artists'):
    stored_user_token = get_user_stored_token()

    if stored_user_token is None:
        return None

    if url is None and type == 'artists':
        url = 'https://api.spotify.com/v1/me/following?type=artist&limit=50'
    elif url is None and type == 'shows':
        url = 'https://api.spotify.com/v1/me/shows?limit=50'

    db_root, db = get_databases().get(type)

    request = requests.get(url=url, headers={
        'Authorization': f'Bearer {stored_user_token.get("access_token")}'
    })

    if request.status_code == 200:
        if type == 'artists':
            response = request.json().get('artists')
            new_items = response.get('items')
        elif type == 'shows':
            response = request.json()
            new_items = response.get('items')

            for item in new_items:
                del item.get('show')['available_markets']

        followed = followed + new_items
        logging.info(f'{len(new_items)} {type} added to the list')

        if response.get('next') is not None:
            get_user_followed(response.get('next'), followed=followed)
        else:
            db_root.drop_table(type)
            db.insert_multiple(followed)
            return followed
    elif request.status_code == 401 and retry_count < 5:
        logging.warn(f'Followed {type} request failed - {request.status_code} - {request.text}')

        refresh_access_token()
        get_user_followed(url=url, followed=followed, retry_count=retry_count + 1)
    else:
        logging.error(f'Followed {type} request failed - {request.status_code} - {request.text}')


def get_artist_albums(artist, retry_count=0, success=True):
    stored_user_token = get_user_stored_token()

    if stored_user_token is None:
        return None

    include_groups = f'include_groups={"%2C".join(params.get("include_groups"))}&'

    request_url = f'https://api.spotify.com/v1/artists/{artist.get("id")}/albums?{include_groups}limit={params.get("albums_request_limit")}'
    request_headers = {
        'Authorization': f'Bearer {stored_user_token.get("access_token")}'
    }

    request_response = requests.get(request_url, headers=request_headers)

    if request_response.status_code == 200:
        success = True
        save_releases_to_database(request_response.json().get('items'), element=artist, type='releases')
    elif request_response.status_code == 401 and retry_count < 5:
        success = False
        logging.warn(
            f'{artist.get("name")} ({artist.get("id")}) albums query failed - {request_response.status_code} - {request_response.text}')

        refresh_access_token()
        get_artist_albums(artist=artist, retry_count=retry_count + 1, success=success)
    else:
        success = False
        logging.error(
            f'{artist.get("name")} ({artist.get("id")}) albums query failed - {request_response.status_code} - {request_response.text}')

    return success, artist, request_response


def get_show_episodes(show, retry_count=0, success=True):
    stored_user_token = get_user_stored_token()

    if stored_user_token is None:
        return None

    request_url = f'https://api.spotify.com/v1/shows/{show.get("show").get("id")}/episodes?limit={params.get("albums_request_limit")}'
    request_headers = {
        'Authorization': f'Bearer {stored_user_token.get("access_token")}'
    }

    request_response = requests.get(request_url, headers=request_headers)

    if request_response.status_code == 200:
        success = True
        save_releases_to_database(request_response.json().get('items'), element=show, type='episodes')
    elif request_response.status_code == 401 and retry_count < 5:
        success = False
        logging.warn(
            f'{show.get("show").get("name")} ({show.get("show").get("id")}) episodes query failed - {request_response.status_code} - {request_response.text}')

        refresh_access_token()
        get_show_episodes(show=show, retry_count=retry_count + 1, success=success)
    else:
        success = False
        logging.error(
            f'{show.get("show").get("name")} ({show.get("show").get("id")}) episodes query failed - {request_response.status_code} - {request_response.text}')

    return success, show, request_response


def save_releases_to_database(items, element=None, type='releases'):
    current_date = datetime.datetime.now()
    newer_than_date = current_date - timedelta(days=params.get('newer_than'))

    items_to_add = []

    if type == 'episodes':
        element = element.get('show')

    db_root, db = get_databases().get(type)

    for item in items:
        date_format = {
            'day': '%Y-%m-%d',
            'month': '%Y-%m',
            'year': '%Y'
        }

        release_date = datetime.datetime.strptime(item.get('release_date'),
                                                  date_format.get(item.get('release_date_precision')))

        if release_date > newer_than_date:
            item['release_date_timestamp'] = release_date.timestamp()
            item['added_date_timestamp'] = current_date.timestamp()

            try:
                del item['available_markets']
            except KeyError:
                pass

            q = Query()

            if not db.search(q.id == item.get('id')):
                if type == 'releases':
                    logging.info(
                        f'{type} : {element.get("name")} ({element.get("id")}) : {item.get("release_date")} - {item.get("total_tracks")} tracks - ({item.get("id")}) {item.get("name")}')
                elif type == 'episodes':
                    logging.info(
                        f'{type} : {element.get("name")} ({element.get("id")}) : {item.get("release_date")} - {item.get("duration_ms")} ms - ({item.get("id")}) {item.get("name")}')
                items_to_add.append(item)

    inserted = db.insert_multiple(items_to_add)
    logging.info(f'{type} : {element.get("name")} ({element.get("id")}) {len(inserted)} new entries')


def remove_outdated_releases_from_db():
    current_date = datetime.datetime.now()
    newer_than_date = current_date - timedelta(days=params.get('newer_than'))
    q = Query()

    removed_albums = db_releases.remove(q.release_date_timestamp < newer_than_date.timestamp())
    removed_episodes = db_episodes.remove(q.release_date_timestamp < newer_than_date.timestamp())

    logging.info(f'Entries removed : {len(removed_albums)} albums, {len(removed_episodes)} episodes')


current_analysis_status = None


def get_analysis_status():
    return current_analysis_status


def perform_search(artists=None, shows=None):
    global current_analysis_status
    if get_analysis_status() is not None:
        logging.warning('An analysis is already running')
        return

    if artists is None:
        artists = db_artists.all()

    if shows is None:
        shows = db_shows.all()

    current_artist = 0
    current_show = 0
    total_artists = len(artists)
    total_shows = len(shows)

    current_analysis_status = {
        'current_artist': current_artist,
        'total_artists': total_artists,
        'current_show': current_show,
        'total_shows': total_shows
    }

    albums_results = []
    episodes_results = []

    for artist in artists:
        current_analysis_status['current_artist'] = current_artist
        current_analysis_status['total_artists'] = total_artists

        current_artist = current_artist + 1
        albums_results.append(get_artist_albums(artist))

        time.sleep(params.get('delay'))

    for show in shows:
        current_analysis_status['current_show'] = current_show
        current_analysis_status['total_shows'] = total_shows

        current_show = current_show + 1
        episodes_results.append(get_show_episodes(show))
        time.sleep(params.get('delay'))

    remove_outdated_releases_from_db()
    current_analysis_status = None
    update_metadata(albums_results=albums_results, episodes_results=episodes_results)

    rss_feed_generator.generate_feed()


def get_artists():
    return db_artists.all()


def get_releases():
    return db_releases.all()


def get_metadata():
    if db_metadata.all() is not None and len(db_metadata.all()) > 0:
        return db_metadata.all()[0]
    else:
        return None


def update_metadata(albums_results=[], episodes_results=[]):
    current_date = datetime.datetime.now()

    last_metadata = get_metadata()
    if last_metadata is not None:
        last_successful_execution = last_metadata.get('last_successful_execution_timestamp')
    else:
        last_successful_execution = None

    if last_successful_execution is not None:
        last_successful_execution = datetime.datetime.fromtimestamp(last_successful_execution)

    db_root_metadata.drop_table('metadata')

    albums_errors = []
    episodes_errors = []

    for result in albums_results:
        (status, item, response) = result

        if not status:
            albums_errors.append({
                'status_code' : response.status_code,
                'message' : response.text,
                'artist_name' : item.get('name'),
                'artist_id' : item.get('id'),
            })

    for result in episodes_results:
        (status, item, response) = result

        if not status:
            episodes_errors.append({
                'status_code' : response.status_code,
                'message' : response.text,
                'show_name' : item.get('show').get('name'),
                'show_id' : item.get('show').get('id'),
            })

    if len(episodes_errors) == 0 and len(albums_errors) == 0:
        last_successful_execution = current_date
    else:
        last_successful_execution = last_successful_execution

    metadata_object = {
        'last_execution_timestamp': current_date.timestamp(),
        'last_execution': current_date.strftime('%Y-%m-%d - %H:%M'),
        'last_successful_execution_timestamp' : last_successful_execution.timestamp(),
        'last_successful_execution' : last_successful_execution.strftime('%Y-%m-%d - %H:%M'),
        'nb_artists': len(get_artists()),
        'nb_releases': len(get_releases()),
        'nb_shows': len(get_shows()),
        'nb_episodes': len(get_episodes()),
        'albums_errors' : albums_errors,
        'episodes_errors' : episodes_errors
    }
    db_metadata.insert(metadata_object)


def get_releases_from_date(date, type):
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    end_date = date.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()

    db_root, db = get_databases().get(type)

    q = Query()
    return db.search((q.release_date_timestamp >= start_date) & (q.release_date_timestamp <= end_date))


def get_parameters():
    return params


def get_databases():
    return {
        'users': (db_root_users, db_users),
        'artists': (db_root_artists, db_artists),
        'releases': (db_root_releases, db_releases),
        'metadata': (db_root_metadata, db_metadata),
        'shows': (db_root_shows, db_shows),
        'episodes': (db_root_episodes, db_episodes)
    }


def get_shows():
    return db_shows.all()


def get_episodes():
    return db_episodes.all()

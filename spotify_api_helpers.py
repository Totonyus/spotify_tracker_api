import base64
import datetime
import time
import uuid
from datetime import timedelta

import requests
from requests import Request
from tinydb import TinyDB, Query

import params_utils

db_root = TinyDB('data/database.json')
db_root_users = TinyDB('data/database_users.json')
db_users = db_root_users.table('users', cache_size=0)
db_root_artists = TinyDB('data/database_artists.json')
db_artists = db_root_artists.table('artists', cache_size=0)
db_root_releases = TinyDB('data/database_releases.json')
db_releases = db_root_releases.table('releases', cache_size=0)
db_root_metadata = TinyDB('data/database_metadata.json')
db_metadata = db_root_metadata.table('metadata', cache_size=0)

params = params_utils.ConfigManager()
client_id = params.get('client_id')
client_secret = params.get('client_secret')
authorization = f'Basic {base64.b64encode((f"{client_id}:{client_secret}").encode("ascii")).decode("ascii")}'

logging = params.get_logger()

def get_authorization_code_url():
    scope = 'user-follow-read'
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
        found = db_users.get(doc_id=1)
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
            logging.info(f'Stored user access_token expired on {current_date}, requesting a new one')
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

    else:
        logging.error(f'access_token refresh query failed - {refresh_query.status_code} - {refresh_query.text}')

    return refresh_query


def get_user_followed_artists(url=None, followed_artists=[], retry_count=0):
    stored_user_token = get_user_stored_token()

    if stored_user_token is None:
        return None

    if url is None:
        url = "https://api.spotify.com/v1/me/following?type=artist&limit=50"

    request = requests.get(url=url, headers={
        'Authorization': f'Bearer {stored_user_token.get("access_token")}'
    })

    if request.status_code == 200:
        response = request.json().get('artists')
        new_items = response.get('items')
        followed_artists = followed_artists + new_items
        logging.info(f'{len(new_items)} artists added to the list')

        if response.get('next') is not None:
            get_user_followed_artists(response.get('next'), followed_artists=followed_artists)
        else:
            db_root_artists.drop_table('artists')
            db_artists.insert_multiple(followed_artists)
            return followed_artists
    elif request.status_code == 401 and retry_count < 5:
        refresh_access_token()
        get_user_followed_artists(url=url, followed_artists=followed_artists, retry_count=retry_count + 1)
    else:
        logging.error(f'Followed artists request failed - {request.status_code} - {request.text}')


def get_artist_albums(artist, retry_count=0):
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
        save_albums_to_database(request_response.json().get('items'), artist=artist)
    elif request_response.status_code == 401 and retry_count < 5:
        refresh_access_token()
        get_artist_albums(artist=artist, retry_count=retry_count + 1)
    else:
        logging.error(
            f'{artist.get("name")} ({artist.get("id")}) albums query failed - {request_response.status_code} - {request_response.text}')


def save_albums_to_database(items, artist=None):
    current_date = datetime.datetime.now()
    newer_than_date = current_date - timedelta(days=params.get('newer_than'))

    items_to_add = []

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
            del item['available_markets']

            q = Query()
            if not db_releases.search(q.id == item.get('id')):
                logging.info(
                    f'{artist.get("name")} ({artist.get("id")}) : {item.get("release_date")} - {item.get("total_tracks")} tracks - ({item.get("id")}) {item.get("name")}')
                items_to_add.append(item)

    inserted = db_releases.insert_multiple(items_to_add)
    logging.info(f'{artist.get("name")} ({artist.get("id")}) {len(inserted)} new entries')


def remove_older_albums_from_db():
    current_date = datetime.datetime.now()
    newer_than_date = current_date - timedelta(days=params.get('newer_than'))
    q = Query()

    removed_entries = db_releases.remove(q.release_date_timestamp < newer_than_date.timestamp())
    logging.info(f'Entries removed : {len(removed_entries)}')


current_analysis_status = None


def get_analysis_status():
    return current_analysis_status


def perform_search(artists=None):
    global current_analysis_status
    if get_analysis_status() is not None:
        logging.warning('An analysis is already running')
        return

    if artists is None:
        artists = db_artists.all()

    logging.warning('No artist found')
    current_artist = 0
    total_artists = len(artists)

    for artist in artists:
        current_analysis_status = {
            'current_artist': current_artist,
            'total_artists': total_artists
        }

        current_artist = current_artist + 1
        get_artist_albums(artist)
        time.sleep(params.get('delay'))

    current_analysis_status = None
    update_metadata()


def get_artists():
    return db_artists.all()


def get_releases():
    return db_releases.all()


def get_metadata():
    if db_metadata.all() is not None and len(db_metadata.all()) > 0:
        return db_metadata.all()[0]
    else:
        return None


def update_metadata():
    current_date = datetime.datetime.now()

    db_root_metadata.drop_table('metadata')

    metadata_object = {
        'last_execution_timestamp': current_date.timestamp(),
        'last_execution': current_date.strftime('%Y-%m-%d - %H:%M'),
    }
    db_metadata.insert(metadata_object)


def get_releases_from_date(date):
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    end_date = date.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()

    q = Query()
    return db_releases.search((q.release_date_timestamp >= start_date) & (q.release_date_timestamp <= end_date))

def get_parameters():
    return params
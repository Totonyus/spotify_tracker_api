import asyncio
import base64
import datetime
import time
import uuid
from datetime import timedelta

import requests
from requests import Request
from tinydb import TinyDB, Query

import params_utils
import rss_feed_generator
from ws_manager import ConnectionManager

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
ws_manager = ConnectionManager()


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
            f'Unable to retrieve user in database, please connect your spotify account here : {params.get("application_url")}/login')
        return None

    if found is None:
        logging.error(
            f'No user found, please connect your spotify account here : {params.get("application_url")}/login')
        return None
    else:
        current_date = datetime.datetime.now()

        if found.get('expires_on') < current_date.timestamp() and refresh is True:
            logging.info(
                f'Stored user access_token expired on {datetime.datetime.fromtimestamp(found.get("expires_on"))}, requesting a new one')
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

    elif auth_query.status_code in [400, 429]:
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

    elif refresh_query.status_code in [400, 429]:
        raise PermissionError(f'{refresh_query.status_code} - {refresh_query.text}')
    else:
        logging.error(f'access_token refresh query failed - {refresh_query.status_code} - {refresh_query.text}')

    return refresh_query


def shows_api_call_handler(request):
    response = request.json()
    new_items = response.get('items')

    for item in new_items:
        del item.get('show')['available_markets']

    return response, new_items


def get_from_api(type, next_url=None, items_retrieved=[], retry_count=0, item=None):
    stored_user_token = get_user_stored_token()

    if stored_user_token is None:
        return None

    db_root, db = get_databases().get(type)

    config = {
        'artists': {
            'url': lambda x: [('artists', 'https://api.spotify.com/v1/me/following?type=artist&limit=50')],
            'success_callback': lambda x: (x.json().get('artists'), x.json().get('artists').get('items')),
            'drop': True,
            'save_method': db.insert_multiple,
            'running_log': lambda n, g, i=None, t=None: f'{len(n)}/{t} {type} added to the list',
            'error_log': lambda i, r: f'Error while fetching {type} - {r.status_code} - {r.text}',
            'must_continue': lambda i: True
        },
        'shows': {
            'url': lambda x: [('shows', 'https://api.spotify.com/v1/me/shows?limit=50')],
            'success_callback': shows_api_call_handler,
            'drop': True,
            'save_method': db.insert_multiple,
            'running_log': lambda n, g, i=None, t=None: f'{len(n)}/{t} {type} added to the list',
            'error_log': lambda i, r: f'Error while fetching {type} - {r.status_code} - {r.text}',
            'must_continue': lambda i: True
        },
        'episodes': {
            'url': lambda x: [
                ('episode',
                 f'https://api.spotify.com/v1/shows/{x.get("show").get("id")}/episodes?limit={params.get("albums_request_limit")}')],
            'success_callback': lambda x: (x.json(), x.json().get('items')),
            'drop': False,
            'save_method': None,
            'running_log': lambda n, i, g,
                                  t=None: f'{i.get("show").get("name")} ({i.get("show").get("id")}) : {len(n)}/{t} {type} added to the list',
            'error_log': lambda i,
                                r: f'Error while fetching {type} : {i.get("show").get("name")} ({i.get("show").get("id")}) - {r.status_code} - {r.text}',
            'must_continue': lambda i: get_release_date_object(i) > datetime.datetime.now() - timedelta(
                days=params.get('newer_than'))
        },
        'releases': {
            'url': lambda x: [
                (group,
                 f'https://api.spotify.com/v1/artists/{x.get("id")}/albums?include_groups={group}&limit={params.get("albums_request_limit")}')
                for group in params.get("include_groups")],
            'success_callback': lambda x: (x.json(), x.json().get('items')),
            'drop': False,
            'save_method': None,
            'running_log': lambda n, i, g,
                                  t=None: f'{i.get("name")} ({i.get("id")}) : {len(n)}/{t} {type} ({g}) added to the list',
            'error_log': lambda i,
                                r: f'Error while fetching {type} : {i.get("name")} ({i.get("id")}) - {r.status_code} - {r.text}',
            'must_continue': lambda i: None if i is None else get_release_date_object(
                i) > datetime.datetime.now() - timedelta(
                days=params.get('newer_than'))
        }
    }

    if next_url is None:
        urls = config.get(type).get('url')(item)
    else:
        urls = [(type, next_url)]

    for subgroup, url in urls:
        request = requests.get(url=url, headers={
            'Authorization': f'Bearer {stored_user_token.get("access_token")}'
        })

        if request.status_code == 200:
            response, new_items = config.get(type).get('success_callback')(request)

            items_retrieved = items_retrieved + new_items

            try:
                last_item = new_items[-1]
            except IndexError:
                last_item = None

            logging.info(config.get(type).get('running_log')(n=new_items, i=item, t=response.get('total'),
                                                             g=subgroup))

            if response.get('next') is not None and config.get(type).get('must_continue')(last_item):
                items, items_retrieved = get_from_api(type=type, next_url=response.get('next'),
                                               items_retrieved=items_retrieved, item=item)
            else:
                pass
                if config.get(type).get('drop'):
                    db_root.drop_table(type)

                if config.get(type).get('save_method') is not None:
                    config.get(type).get('save_method')(items_retrieved)

        elif request.status_code == 401 and retry_count < 3:
            refresh_access_token()
            item, items_retrieved = get_from_api(type=type, next_url=url, items_retrieved=items_retrieved,
                                                 retry_count=retry_count + 1,
                                                 item=item)
        elif request.status_code == 429 and retry_count < 3:
            time.sleep(5)
            item, items_retrieved = get_from_api(type=type, next_url=url, items_retrieved=items_retrieved,
                                                 retry_count=retry_count + 1,
                                                 item=item)
        else:
            logging.error(logging.info(config.get(type).get('error_log')(i=item, r=request)))

    return item, items_retrieved


def get_release_date_object(item):
    date_format = {
        'day': '%Y-%m-%d',
        'month': '%Y-%m',
        'year': '%Y'
    }

    return datetime.datetime.strptime(item.get('release_date'),
                                      date_format.get(item.get('release_date_precision')))


def save_releases_to_database(items, type):
    current_date = datetime.datetime.now()
    newer_than_date = current_date - timedelta(days=params.get('newer_than'))

    items_to_add = []

    db_root, db = get_databases().get(type)

    for item_category_tuple in items:
        element, item_category = item_category_tuple

        for item in [i for i in item_category if i is not None]:
            release_date = get_release_date_object(item)

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
                            f'{type} : {element.get("show").get("name")} ({element.get("show").get("id")}) : {item.get("release_date")} - {item.get("duration_ms")} ms - ({item.get("id")}) {item.get("name")}')
                    items_to_add.append(item)

    inserted = db.insert_multiple(items_to_add)

    logging.info(f'{type} : {len(inserted)} new entries')


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


def perform_full_search(type=None):
    get_from_api(type='artists')
    get_from_api(type='shows')

    perform_search(type=type)


def perform_search(artists=None, shows=None, type=None):
    loop = asyncio.new_event_loop()

    global current_analysis_status
    if get_analysis_status() is not None:
        logging.warning('An analysis is already running')
        return

    remove_outdated_releases_from_db()

    if artists is None:
        artists = db_artists.all()

    if shows is None:
        shows = db_shows.all()

    current_artist = 1
    current_show = 1
    total_artists = len(artists)
    total_shows = len(shows)

    current_analysis_status = {
        'scan_running': True,
        'current_artist': current_artist,
        'total_artists': total_artists,
        'current_show': current_show,
        'total_shows': total_shows
    }

    loop.run_until_complete(ws_manager.broadcast(current_analysis_status))

    if type is None or type == 'releases' :
        new_releases = []
        for artist in artists:
            current_analysis_status['current_artist'] = current_artist
            current_analysis_status['total_artists'] = total_artists

            current_artist = current_artist + 1
            new_releases.append(get_from_api(type='releases', item=artist))

            loop.run_until_complete(ws_manager.broadcast(current_analysis_status))
            time.sleep(params.get('delay'))

        save_releases_to_database(items=new_releases, type='releases')

    if type is None or type == 'episodes' :
        new_episodes = []
        for show in shows:
            current_analysis_status['current_show'] = current_show
            current_analysis_status['total_shows'] = total_shows

            current_show = current_show + 1
            new_episodes.append(get_from_api(type='episodes', item=show))

            loop.run_until_complete(ws_manager.broadcast(current_analysis_status))
            time.sleep(params.get('delay'))

        save_releases_to_database(items=new_episodes, type='episodes')

    update_metadata()

    rss_feed_generator.generate_feed()

    current_analysis_status['scan_running'] = False
    loop.run_until_complete(ws_manager.broadcast(current_analysis_status))
    current_analysis_status = None


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
        'nb_artists': len(get_artists()),
        'nb_releases': len(get_releases()),
        'nb_shows': len(get_shows()),
        'nb_episodes': len(get_episodes())
    }

    db_metadata.insert(metadata_object)


def get_releases_from_date(date, type, default_sorting=None):
    start_date = date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    end_date = date.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()

    db_root, db = get_databases().get(type)

    q = Query()

    if default_sorting == 'added_date_timestamp' or default_sorting is None:
        reference_date = q.added_date_timestamp
    else:
        reference_date = q.release_date_timestamp

    return db.search((reference_date >= start_date) & (reference_date <= end_date))


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


def get_ws_manager():
    return ws_manager

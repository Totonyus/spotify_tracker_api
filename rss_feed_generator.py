from datetime import datetime
from rfeed import *

import spotify_api_helpers as api

def generate_feed():
    feed_items = []

    releases = api.get_releases()

    for item in releases:
        artists_str = []

        artists = item.get('artists')

        for artist in artists:
            artists_str.append(artist.get('name'))

        feed_items.append(Item(
            title=f'{item.get("artists")[0].get("name")} - {item.get("name")}',
            link=item.get('external_urls').get('spotify'),
            description=f'New {item.get("album_group")} with {item.get("total_tracks")} tracks. Featuring {", ".join(artists_str)}.',
            author='Spotify tracker api',
            guid=Guid(f'release_{item.get("id")}'),
            pubDate=datetime.fromtimestamp(item.get(api.get_parameters().get("default_sorting")))
        ))

    episodes = api.get_episodes()
    for item in episodes:
        feed_items.append(Item(
            title=f'{item.get("name")}',
            link=item.get('external_urls').get('spotify'),
            description=f'New episode of {round(item.get("duration_ms") / 1000 / 60)} minutes. Description : {item.get("description")}',
            author='Spotify tracker api',
            guid=Guid(f'episode_{item.get("id")}'),
            pubDate=datetime.fromtimestamp(item.get(api.get_parameters().get("default_sorting")))
        ))

    feed = Feed(
        title="Spotify Tracker",
        link=f'{api.get_parameters().get("application_url")}/static/feed',
        description='The rss feed to follow your artists and podcasts releases',
        language='en-US',
        lastBuildDate=datetime.now(),
        items=feed_items
    )

    file = open('static/feed', 'w')
    file.write(feed.rss())
    file.close()

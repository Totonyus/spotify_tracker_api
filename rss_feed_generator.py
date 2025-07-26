import jinja2
from datetime import datetime
import spotify_api_helpers as api

def generate_feed():
    loader = jinja2.FileSystemLoader('./templates')
    env = jinja2.Environment(autoescape=True, loader=loader)

    template = env.get_template('rss_feed.xml.j2')
    render = template.render({
        'api': api,
        'releases': api.get_releases(),
        'episodes': api.get_episodes(),
        'datetime': datetime
    })

    rss_feed = open('static/feed', 'w')
    rss_feed.write(render)
    rss_feed.close()

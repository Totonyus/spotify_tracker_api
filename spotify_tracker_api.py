from datetime import datetime
from logging import handlers

import uvicorn
from fastapi import FastAPI, Response, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import params_utils
import spotify_api_helpers as api
from fastapi import FastAPI
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="./templates")

params = api.get_parameters()
logging = params.get_logger()


@app.get('/login', response_class=RedirectResponse, status_code=302)
async def login():
    return api.get_authorization_code_url()


@app.get('/auth')
async def auth(response: Response, background_tasks: BackgroundTasks, code, state):
    if state is None:
        response.status_code = 400

    query_result = api.request_access_token(code)

    if query_result.status_code != 200:
        return RedirectResponse(api.get_authorization_code_url())
    else:
        api.get_user_followed(type='artists')
        api.get_user_followed(type='shows')

        api.update_metadata()

        background_tasks.add_task(api.perform_search)

    return RedirectResponse('/')


@app.get('/api/artists')
async def artists():
    return api.get_artists()


@app.get('/artists')
async def artists(request: Request, sort_by='name', reverse_sort='false'):
    return templates.TemplateResponse(name="artists.html.j2", request=request,
                                      context={'artists': api.get_artists(),
                                               'metadata': api.get_metadata(),
                                               'status': api.get_analysis_status(),
                                               'app_params': params.get_all(),
                                               'sort_by': sort_by,
                                               'reverse_sort': reverse_sort == 'true'
                                               }
                                      )


@app.get('/api/shows')
async def shows():
    return api.get_shows()


@app.get('/shows')
async def shows(request: Request, sort_by='show.name', reverse_sort='false'):
    return templates.TemplateResponse(name="shows.html.j2", request=request,
                                      context={'shows': api.get_shows(),
                                               'metadata': api.get_metadata(),
                                               'status': api.get_analysis_status(),
                                               'app_params': params.get_all(),
                                               'sort_by': sort_by,
                                               'reverse_sort': reverse_sort == 'true'
                                               }
                                      )


@app.get('/api/episodes')
async def episodes():
    return api.get_episodes()


@app.get('/episodes')
async def episodes(request: Request, sort_by='release_date_timestamp', reverse_sort='true'):
    return templates.TemplateResponse(name="episodes.html.j2", request=request,
                                      context={'episodes': api.get_episodes(),
                                               'metadata': api.get_metadata(),
                                               'shows': api.get_shows(),
                                               'status': api.get_analysis_status(),
                                               'app_params': params.get_all(),
                                               'sort_by': sort_by,
                                               'reverse_sort': reverse_sort == 'true'
                                               }
                                      )


@app.get('/api/releases')
async def releases():
    return api.get_releases()


@app.get('/releases')
async def releases(request: Request, sort_by='release_date_timestamp', reverse_sort='true'):
    return templates.TemplateResponse(name="releases.html.j2", request=request,
                                      context={'artists': api.get_artists(),
                                               'releases': api.get_releases(),
                                               'metadata': api.get_metadata(),
                                               'app_params': params.get_all(),
                                               'status': api.get_analysis_status(),
                                               'sort_by': sort_by,
                                               'reverse_sort': reverse_sort == 'true'
                                               }
                                      )


@app.get('/refresh')
async def refresh(background_tasks: BackgroundTasks, request: Request):
    if api.get_user_stored_token() is None:
        return RedirectResponse('/login')

    api.get_user_followed(type='artists')
    api.get_user_followed(type='shows')
    background_tasks.add_task(api.perform_search)

    referer = request.headers.get('referer')

    if referer is None:
        return RedirectResponse('/')

    return RedirectResponse(referer)


@app.get('/api/latest')
async def from_fate(date=None):
    return get_all_latest_releases(date)


def get_all_latest_releases(date=None):
    if date is None:
        date = datetime.now()
    else:
        date = datetime.strptime(date, '%Y-%m-%d')

    return {
        'releases': api.get_releases_from_date(date, type='releases'),
        'episodes': api.get_releases_from_date(date, type='episodes'),
        'metadata': api.get_metadata()
    }


@app.get('/')
async def landing_page(request: Request):
    return templates.TemplateResponse(name="landing_page.html.j2", request=request,
                                      context={
                                          'metadata': api.get_metadata(),
                                          'app_params': params.get_all(),
                                          'user': api.get_user_stored_token(refresh=False) is not None,
                                          'latest': get_all_latest_releases(date=None),
                                          'status': api.get_analysis_status()}
                                      )


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    trigger = CronTrigger.from_crontab(params.get('cron'))
    scheduler.add_job(api.perform_search, trigger)
    scheduler.start()

    uvicorn.run(app, port=params.get('listen_port'), host=params.get('listen_host'))

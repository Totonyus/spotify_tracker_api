import uvicorn
from fastapi import FastAPI, Response, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import spotify_api_helpers as api
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import rss_feed_generator

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

    try:
        query_result = api.request_access_token(code)
    except PermissionError as e:
        logging.critical(f'Cannot authenticate user : {e}')
        return RedirectResponse('/?error_flag=true')

    if query_result.status_code != 200:
        return RedirectResponse(api.get_authorization_code_url())
    else:
        try:
            background_tasks.add_task(api.perform_full_search)
        except PermissionError as e:
            logging.critical(f'Cannot re-authenticate user : {e}')
            return RedirectResponse('/login')

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
async def episodes(request: Request, sort_by=api.get_parameters().get("default_sorting"), reverse_sort='true'):
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
async def releases(request: Request, sort_by=api.get_parameters().get("default_sorting"), reverse_sort='true'):
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
    try:
        if api.get_user_stored_token() is None:
            return RedirectResponse('/login')

        background_tasks.add_task(api.perform_full_search)
    except PermissionError as e:
        logging.critical(e)
        return RedirectResponse('/login')

    referer = request.headers.get('referer')

    if referer is None:
        return RedirectResponse('/')

    return RedirectResponse(referer)


@app.get('/api/refresh')
async def refresh(background_tasks: BackgroundTasks, request: Request, response: Response):
    try:
        if api.get_user_stored_token() is None:
            response.status_code = 400
            return {'message': 'no user logged'}

        background_tasks.add_task(api.perform_full_search)
    except PermissionError as e:
        logging.critical(e)
        response.status_code = 400
        return {'message': str(e)}

    return None


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


@app.websocket("/ws/refresh_status")
async def websocket_endpoint(websocket: WebSocket):
    await api.get_ws_manager().connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        api.get_ws_manager().disconnect(websocket)


@app.get('/')
async def landing_page(request: Request):
    return templates.TemplateResponse(name="landing_page.html.j2", request=request,
                                      context={
                                          'metadata': api.get_metadata(),
                                          'app_params': params.get_all(),
                                          'user': api.get_user_stored_token(refresh=False) is not None,
                                          'latest': get_all_latest_releases(date=None),
                                          'status': api.get_analysis_status()
                                      })


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    trigger = CronTrigger.from_crontab(params.get('cron'))
    scheduler.add_job(api.perform_full_search, trigger)
    scheduler.start()

    rss_feed_generator.generate_feed()

    uvicorn.run(app, port=params.get('listen_port'), host=params.get('listen_host'))

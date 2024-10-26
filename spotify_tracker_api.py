from datetime import datetime
from logging import handlers

import uvicorn
from fastapi import FastAPI, Response, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

import params_utils
import spotify_api_helpers as api
from fastapi import FastAPI
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()
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
        api.get_user_followed_artists()

    return RedirectResponse('/artists')


@app.get('/api/artists')
async def artists():
    return api.get_artists()


@app.get('/artists')
async def artists(request: Request):
    if api.get_user_stored_token() is None:
        return RedirectResponse('/login')

    templates = Jinja2Templates(directory="./templates")

    return templates.TemplateResponse(name="artists.html.j2", request=request,
                                      context={'artists': api.get_artists(),
                                               'metadata': api.get_metadata(),
                                               'app_params': params.get_all()}
                                      )


@app.get('/api/releases')
async def releases():
    return api.get_releases()


@app.get('/releases')
async def releases(request: Request):
    if api.get_user_stored_token() is None:
        return RedirectResponse('/login')

    templates = Jinja2Templates(directory="./templates")

    return templates.TemplateResponse(name="releases.html.j2", request=request,
                                      context={'artists': api.get_artists(),
                                               'releases': api.get_releases(),
                                               'metadata': api.get_metadata(),
                                               'app_params': params.get_all(),
                                               'status': api.get_analysis_status()}
                                      )


@app.get('/refresh')
async def refresh(background_tasks: BackgroundTasks):
    if api.get_user_stored_token() is None:
        return RedirectResponse('/login')

    background_tasks.add_task(api.perform_search)

    return RedirectResponse('/releases')


@app.get('/api/latest')
async def from_fate(date=None):
    if date is None:
        date = datetime.now()
    else:
        date = datetime.strptime(date, '%Y-%m-%d')

    return {
        'items': api.get_releases_from_date(date),
        'metadata': api.get_metadata()
    }


### To display the login message at the initial launch
api.get_user_stored_token(refresh=False)

if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    trigger = CronTrigger.from_crontab(params.get('cron'))
    scheduler.add_job(api.perform_search, trigger)
    scheduler.start()

    uvicorn.run(app, port=params.get('listen_port'), host=params.get('listen_host'))

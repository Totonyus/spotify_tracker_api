# What is it ?

It's a small (and simple) self-hosted application to extract the latest releases of the artists you follow on spotify. As far as I know there is no such tool that is efficient AND free.

This app is meant to be simple an easy. There is no advanced features that are planned.

# Prerequisites

To get your `client_id` and your `client_secret` you need to create an application on your Spotify developer console following this [official guide](https://developer.spotify.com/documentation/web-api/tutorials/getting-started#create-an-app)

Redirect-uri must use the route `/auth`. Example : `http://localhost:8000/auth`

# Installation
## With docker
By simply using the docker-compose file provided.

## Without docker
```
pip3 install -r requirements
```

```
python3 spotify_tracker_api.py
```

# Configuration
## Add application secret_id
There are a few parameters that are set in [the parameters file](https://github.com/Totonyus/spotify_tracker_api/blob/main/params/params.ini)

The application won't start if `client_id`, `secret_id` or `application_url` are not provided.

# Setup application
Go on the url `http://localhost:8000/login`. You will be redirected on spotify login page and will be asked permission to use your account information.

If everything is OK you'll be redirected on the page landing page.

To launch the first scan, simply go to this url http://localhost:8000/refresh. A counter appears on the landing page : "Running scan : 36 on 112". Manually reload the page to get the progression.

# API endpoints
## GET /
The landing page of the application 

![landing_page.png](screenshots%2Flanding_page.png)

## GET /login
Simple redirects on spotify login page to allow application

## GET /auth
To ask permission on your spotify account

## GET /api/artists
The artists you follow in json

## GET /artists
The artists you follow but with UI

![artists_page.png](screenshots%2Fartists_page.png)

## GET /api/releases
The latest releases of your artists in json

## GET /releases
The lates releases of your artists but with UI

![releases_pages.png](screenshots%2Freleases_pages.png)

## GET /api/shows
The shows you follow in json

## GET /shows
The shows you follow but with UI

![shows_page.png](screenshots%2Fshows_page.png)

## GET /api/episodes
The latest episodes of your shows in json

## GET /episodes
The latest episodes of your shows but with UI

![episodes_pages.png](screenshots%2Fepisodes_page.png)

## GET /refresh
Launch a new analysis to find the latest releases. The endpoint will simply ignore requests an analysis is already running.

## GET /api/refresh
Same as `/refresh` but more adapted to api usage

## GET /api/latest
Optional parameter : date (`YYYY-MM-DD`)

Will return (in json) all releases on a given date (based on what it's in the database). If `date` is not provided, will return today releases.

This endpoint is meant to have a simple way to get new releases in an exploitable format for automation purpose.

Example :
- Launch a refresh at 01:00
- Retrieve all today releases with this endpoint and send a notification

## GET /static/feed
The rss feed of all new album releases and new podcasts
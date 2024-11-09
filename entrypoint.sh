#!/bin/bash

echo ~~~ ydl_api_ng
echo ~~~ Revision : $GIT_BRANCH - $GIT_REVISION
echo ~~~ Docker image generated : $DATE

mkdir -p /app/logs /app/params /app/data

if [ ! -e '/app/params/params.ini' ]; then
  cp -n /app/setup/params.ini /app/params/
fi

if [ ! -e /app/data/database_artists.json ]; then
  touch /app/data/database_artists.json /app/data/database_metadata.json /app/data/database_releases.json /app/data/database_users.json
fi

chmod a+x entrypoint.sh

if [ "$DEBUG" == "DEBUG" ]; then
  echo ~~~ Launching DEBUG mode ~~~
  su "$(id -un $UID)" -c "uvicorn spotify_tracker_api:app --reload --port 8000 --host 0.0.0.0 --reload-include='templates/*.j2' --reload-include='static/*.css' --reload-include='static/*.js'"
else
  su "$(id -un $UID)" -c "python3 spotify_tracker_api.py"
fi

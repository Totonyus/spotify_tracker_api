# syntax=docker/dockerfile:1

FROM python:3.12-slim-bullseye
WORKDIR /app

ARG GIT_BRANCH=unknown GIT_REVISION=unknown DATE=unknown TARGET_ARCH='amd'
ENV GIT_BRANCH=$GIT_BRANCH GIT_REVISION=$GIT_REVISION DATE=$DATE LOG_LEVEL="info" TARGET_ARCH=$TARGET_ARCH
VOLUME ["/app/params", "/app/data", "/app/logs"]
EXPOSE 80

COPY --chmod=755 entrypoint.sh ./
COPY *.py pip_requirements ./
COPY params/params.ini ./setup/
COPY templates/* ./templates/
COPY static/* ./static/

RUN pip3 install --disable-pip-version-check -q --root-user-action=ignore -r pip_requirements

ENTRYPOINT ["/app/entrypoint.sh"]

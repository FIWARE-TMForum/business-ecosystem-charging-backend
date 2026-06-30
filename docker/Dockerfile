FROM ubuntu:20.04

LABEL MAINTAINER="Future Internet Consulting and Development Solutions S.L."

ENV LOGLEVEL=info
ENV VERSION=master
ARG DEBIAN_FRONTEND=noninteractive

RUN mkdir /opt/business-ecosystem-charging-backend/
WORKDIR /opt/business-ecosystem-charging-backend/

COPY requirements.txt requirements.txt
COPY dev-requirements.txt dev-requirements.txt
COPY src/ src/

RUN apt-get update && apt-get -y install python3 python3-pip gcc git wkhtmltopdf xvfb wget cron && \
    pip3 install -r requirements.txt && pip3 install -r dev-requirements.txt && \
    mkdir ./src/media && mkdir ./src/media/bills && mkdir ./src/media/assets && mkdir ./src/plugins

COPY ./docker/entrypoint.sh /

EXPOSE 8006

ENTRYPOINT ["/entrypoint.sh"]


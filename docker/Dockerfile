FROM ubuntu:24.04

LABEL MAINTAINER="Future Internet Consulting and Development Solutions S.L."

ENV LOGLEVEL=info
ENV VERSION=master
ARG DEBIAN_FRONTEND=noninteractive

RUN mkdir /opt/business-ecosystem-charging-backend/
WORKDIR /opt/business-ecosystem-charging-backend/

COPY requirements.txt requirements.txt
COPY dev-requirements.txt dev-requirements.txt
COPY src/ src/

RUN apt-get update && apt-get -y install --no-install-recommends \
    cron \
    gcc \
    git \
    software-properties-common \
    wget \
    wkhtmltopdf \
    xvfb && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get -y install --no-install-recommends python3.9 python3.9-distutils && \
    wget -O /tmp/get-pip.py https://bootstrap.pypa.io/pip/3.9/get-pip.py && \
    python3.9 /tmp/get-pip.py && \
    python3.9 -m pip install --no-cache-dir --ignore-installed -r requirements.txt && \
    python3.9 -m pip install --no-cache-dir --ignore-installed -r dev-requirements.txt && \
    mkdir -p ./src/media/bills ./src/media/assets ./src/plugins && \
    rm -rf /tmp/get-pip.py /var/lib/apt/lists/*

COPY ./docker/entrypoint.sh /

EXPOSE 8006

ENTRYPOINT ["/entrypoint.sh"]

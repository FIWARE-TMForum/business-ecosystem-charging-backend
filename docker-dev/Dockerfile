FROM ubuntu:24.04

LABEL Maintainer="Future Internet Consulting and Development Solutions S.L."

ARG DEBIAN_FRONTEND=noninteractive

COPY requirements.txt requirements.txt
COPY dev-requirements.txt dev-requirements.txt

RUN apt-get update && \
    apt-get -y install --no-install-recommends \
        software-properties-common \
        vim \
        wget \
        xvfb && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get -y install --no-install-recommends python3.9 python3.9-distutils && \
    wget -O /tmp/get-pip.py https://bootstrap.pypa.io/pip/3.9/get-pip.py && \
    python3.9 /tmp/get-pip.py && \
    python3.9 -m pip install --no-cache-dir --ignore-installed -r requirements.txt && \
    python3.9 -m pip install --no-cache-dir --ignore-installed -r dev-requirements.txt && \
    rm -rf /tmp/get-pip.py /var/lib/apt/lists/*
RUN mkdir -p business-ecosystem-charging-backend/src
RUN echo "#!/bin/bash" > /entrypoint.sh
RUN echo "while true; do sleep 1000; done" >> /entrypoint.sh && chmod +x /entrypoint.sh

# Create volume for the software under development
VOLUME /business-ecosystem-charging-backend/src

EXPOSE 8006

ENTRYPOINT ["/entrypoint.sh"]

#!/usr/bin/env bash

function test_connection {
    echo "Testing $1 connection"
    exec 10<>/dev/tcp/$2/$3
    STATUS=$?
    I=0

    while [[ ${STATUS} -ne 0  && ${I} -lt 50 ]]; do
        echo "Connection refused, retrying in 5 seconds..."
        sleep 5

        if [[ ${STATUS} -ne 0 ]]; then
            exec 10<>/dev/tcp/$2/$3
            STATUS=$?

        fi
        I=${I}+1
    done

    exec 10>&- # close output connection
    exec 10<&- # close input connection

    if [[ ${STATUS} -ne 0 ]]; then
        echo "It has not been possible to connect to $1"
        exit 1
    fi

    echo "$1 connection, OK"
}

if [ ! -f /opt/business-ecosystem-charging-backend/src/__init__.py ]; then
    touch /opt/business-ecosystem-charging-backend/src/__init__.py
fi

# Create __init__.py file if not present (a volume has been bound)
if [ ! -f /opt/business-ecosystem-charging-backend/src/wstore/asset_manager/resource_plugins/plugins/__init__.py ]; then
    touch /opt/business-ecosystem-charging-backend/src/wstore/asset_manager/resource_plugins/plugins/__init__.py
fi

cd /opt/business-ecosystem-charging-backend/src

# Ensure mongodb is running
# Get MongoDB host and port from settings

if [ -z ${BAE_CB_MONGO_SERVER} ]; then
    MONGO_HOST=`grep -o "'host':.*" ./settings.py | grep -o ": '.*'" | grep -oE "[^:' ]+"`

    if [ -z ${MONGO_HOST} ]; then
        MONGO_HOST=localhost
    fi
else
    MONGO_HOST=${BAE_CB_MONGO_SERVER}
fi

if [ -z ${BAE_CB_MONGO_PORT} ]; then
    MONGO_PORT=`grep -o "'port':.*" ./settings.py | grep -o ": '.*'" | grep -oE "[^:' ]+"`

    if [ -z ${MONGO_PORT} ]; then
        MONGO_PORT=27017
    fi
else
    MONGO_PORT=${BAE_CB_MONGO_PORT}
fi

test_connection "MongoDB" ${MONGO_HOST} ${MONGO_PORT}

echo "Starting charging server"

python3 manage.py migrate

# Register and start the billing/payment scheduler cron jobs (settings.CRONJOBS),
# only when this backend owns the billing engine
if [ "${BAE_CB_BILLING_ENGINE}" = "local" ]; then
    python3 manage.py crontab remove
    python3 manage.py crontab add
    service cron start
fi

gunicorn wsgi:application --workers 1 --forwarded-allow-ips "*" --log-file - --bind 0.0.0.0:8006 --log-level ${LOGLEVEL}

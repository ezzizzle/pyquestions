#!/bin/bash

PYQA_WORKER_COUNT=${PYQA_WORKER_COUNT:-1}

if [ "$PYQA_DEBUG" = "true" ]; then
    echo "Running in debug mode with Flask"
    export FLASK_RUN_PORT=8000
    exec flask --debug run -h 0.0.0.0
else
    exec gunicorn \
        -b 0.0.0.0:8000 \
        --worker-class eventlet \
        -w ${PYQA_WORKER_COUNT} \
        --access-logfile - \
        --access-logformat '%(h)s - %(u)s [%(t)s] "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"' \
        app:app
fi
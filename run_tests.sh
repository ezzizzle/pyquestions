#!/bin/bash

pushd tests

source test.env

if [ "$1" = "coverage" ]; then
    pip install coverage > /dev/null 2>&1
    coverage run -m unittest discover
    coverage html
    open htmlcov/index.html
else
    python3 -m unittest discover
fi

popd

#!/usr/bin/env sh
set -eu
python -m uvicorn dev_app:app --host 127.0.0.1 --port 8000

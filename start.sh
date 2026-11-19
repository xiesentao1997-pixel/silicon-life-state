#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(sys.version_info[:2] < (3, 10))'; then
    echo 'Silicon Life State requires Python 3.10 or newer.' >&2
    exit 1
fi
exec python3 apps/local-service/server.py "$@"

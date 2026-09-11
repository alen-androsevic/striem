#!/bin/sh
export PYTHONPATH="/app/share/striem${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m striem "$@"

#!/bin/bash
set -eu
cd "$(dirname "$0")"
exec python3 -m context_panel.launch "$@"

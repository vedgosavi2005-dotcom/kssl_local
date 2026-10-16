#!/usr/bin/env bash
# bash routines/set2_research/load.sh [--prompt ID] [--dry-run]   loads the reply .json files into kssl_staging
cd "$(dirname "$0")/../.." && python -m prompts.batch load "routines/set2_research/work/${DAY:-$(date +%F)}" "$@"

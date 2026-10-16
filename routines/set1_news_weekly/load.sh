#!/usr/bin/env bash
# bash routines/set1_news_weekly/load.sh [--prompt ID] [--dry-run]   loads the reply .json files into kssl_staging
cd "$(dirname "$0")/../.." && python -m prompts.batch load "routines/set1_news_weekly/work/${DAY:-$(date +%F)}" "$@"

#!/usr/bin/env bash
# bash routines/set1_news_weekly/run.sh [--prompt ID]   runs every exported prompt that has no reply yet through the claude CLI
cd "$(dirname "$0")/../.." && python -m prompts.batch run "routines/set1_news_weekly/work/${DAY:-$(date +%F)}" "$@"

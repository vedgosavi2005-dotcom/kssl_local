#!/usr/bin/env bash
# bash routines/set1_news_weekly/auto.sh [--prompt ID] [--limit N] [--rerun]   export -> run -> load, prompt by prompt in the set's order
cd "$(dirname "$0")/../.." && python -m prompts.batch auto --set set1 --out "routines/set1_news_weekly/work/${DAY:-$(date +%F)}" "$@"

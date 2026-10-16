#!/usr/bin/env bash
# bash routines/set1_news_weekly/export.sh [--prompt ID] [--limit N] [--rerun]   -> work/<today>/   (DAY=2026-10-20 to pick another folder)
cd "$(dirname "$0")/../.." && python -m prompts.batch export --set set1 --out "routines/set1_news_weekly/work/${DAY:-$(date +%F)}" "$@"

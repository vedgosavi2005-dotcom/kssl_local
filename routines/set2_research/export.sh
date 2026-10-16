#!/usr/bin/env bash
# bash routines/set2_research/export.sh [--prompt ID] [--limit N] [--rerun]   -> work/<today>/   (DAY=2026-10-20 to pick another folder)
cd "$(dirname "$0")/../.." && python -m prompts.batch export --set set2 --out "routines/set2_research/work/${DAY:-$(date +%F)}" "$@"

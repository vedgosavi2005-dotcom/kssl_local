#!/usr/bin/env bash
# bash routines/set2_research/auto.sh [--prompt ID] [--limit N] [--rerun]   export -> run -> load, prompt by prompt in the set's order
cd "$(dirname "$0")/../.." && python -m prompts.batch auto --set set2 --out "routines/set2_research/work/${DAY:-$(date +%F)}" "$@"

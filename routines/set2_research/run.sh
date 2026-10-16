#!/usr/bin/env bash
# bash routines/set2_research/run.sh [--prompt ID]   runs every exported prompt that has no reply yet through the claude CLI
cd "$(dirname "$0")/../.." && python -m prompts.batch run "routines/set2_research/work/${DAY:-$(date +%F)}" "$@"

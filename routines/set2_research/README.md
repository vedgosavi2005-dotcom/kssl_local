# Set 2 - Research (web search)

Quarterly, or on demand after the client's Excel (competitors, products, specs) changes. These prompts **need web search** (all except `matchup`),
so a manual run in claude.ai must have web search switched on.

| # | prompt | what it makes | needs | web | time / cost per subject* |
|---|---|---|---|---|---|
| 1 | `partnership` | partners + evidence cards of one competitor | competitors loaded | yes | 207 s, $1.13 |
| 2 | `project` | defence projects of one competitor | competitors; stage + Domestic/Export rows (`07_page_setup.sql`) | yes | 140 s, $0.60 |
| 3 | `geo` | geo footprint of one company: countries, products supplied, client counter-products | competitors, products | yes | 225 s, $0.92 |
| 4 | `matchup` | client product vs competitor product, spec by spec | products and specs from the Excel | no | 62 s, $0.17 |
| 5 | `global_requirement` | requirements of governments and armed forces, per category | technology categories | yes | 263 s, $1.13 |
| 6 | `innovation_discovery` | candidate innovations per technology category | categories; Technology pillar row (`07_page_setup.sql`) | yes | 159 s, $0.86 |
| 7 | `innovation_detail` | detail of one candidate innovation | **`innovation_discovery` loaded first** | yes | 87 s, $0.29 |
| 8 | `patent_classification` | category label per patent filing | patent filings in staging | yes | 41 s, $0.28 |

*From the latest test runs in the local `staging.prompt_run` (one subject = one competitor / category / pair / innovation). Web-search runs take 1-4 minutes each.
The number of subjects per prompt is what `check` shows; a full quarter is typically 10-40 runs, one to two hours of waiting.

**Order matters.** `innovation_detail` reads the innovations that `innovation_discovery` loaded. The others are independent, but keep the table order.
So the set is processed prompt by prompt: export, run, **load**, next prompt (`--prompt ID`). `auto.sh` does that.

## Before you start
1. Tunnel (leave it open): `bash routines/tunnel.sh`. One-time setup (including `07_page_setup.sql` on the VPS): `routines/SETUP.md`.
2. See what is pending: `python -m prompts.batch check --set set2`

## Way A - automatic (claude CLI), whole set
    bash routines/set2_research/auto.sh                        # every pending subject, prompt by prompt (can take hours)
    bash routines/set2_research/auto.sh --limit 1              # a trial: 1 subject per prompt
    bash routines/set2_research/auto.sh --prompt partnership   # one prompt only

## Way B - step by step (also the manual paste way)
For each prompt in the table order:

    bash routines/set2_research/export.sh --prompt partnership     # 1. files in work/<today>/
    bash routines/set2_research/run.sh    --prompt partnership     # 2. Claude CLI (web search on) writes <name>.json  (or by hand, below)
    bash routines/set2_research/load.sh   --prompt partnership     # 3. validate + load into kssl_staging
    # then project, geo, matchup, ... innovation_discovery, then innovation_detail, patent_classification

Options: `export.sh --limit N`, `--rerun` (subjects that already ran at this prompt version, e.g. after the client changed the Excel or the prompt text changed),
`load.sh --dry-run` (validate only: nothing written, nothing logged). `DAY=2026-10-16 bash .../load.sh` selects another day's folder.
Without the wrappers: `python -m prompts.batch export --set set2 --prompt partnership --out routines/set2_research/work/2026-10-16`, then `python -m prompts.batch run <dir>` and `python -m prompts.batch load <dir>`.

### Manual run (instead of step 2)
For each `work/<date>/<name>.prompt.md`: copy from the line `## SYSTEM` to the end, paste into a new claude.ai chat **with web search turned on**
(the header comment says `web_search: yes`), wait for the reply and save it entirely as `<name>.json` in the same folder (fences or a sentence around the JSON are fine).
Then step 3. `run.sh` skips files that already have a `.json`, so you can mix: do some by hand, let the CLI do the rest.

### 4. Approve
the review site (`KSSL_REVIEW_URL` in `.env`) (login in `.env`): review the cards, **Approve**. Live site: the live site (`KSSL_LIVE_URL` in `.env`).

## Folders
    routines/set2_research/work/<date>/             exported <name>.prompt.md + <name>.meta.json (+ <name>.json after the run)
    routines/set2_research/work/<date>/loaded/      processed OK (loaded, or skipped by the model), logged in staging.prompt_run
    routines/set2_research/work/<date>/rejected/    validation failed; <name>.err.txt says why
`<name>` = `<prompt>__<subject key>`. `work/` is gitignored.

## Troubleshooting
- **`open the tunnel first`**: start `routines/tunnel.sh`.
- **`no subjects yet (the subject query returns no rows)`**: the data the prompt needs is not in the VPS database yet (competitors, products, specs, patent filings, or an earlier prompt's output). `check` shows the pending count per prompt. For `project` / `innovation_*` also see the page-setup rows: `routines/SETUP.md` step 6.
- **A file landed in `rejected/`**: read its `.err.txt` (not JSON, value not allowed, name not found, ...). The subject is logged `rejected` and is not offered again by default.
  Fix the `.json` by hand and move the three files back to `work/<date>/`, then `load.sh`; or `export.sh --prompt ID --rerun` and run again.
- **`unresolved=[...]` in a result line**: the model named a competitor/product/location that does not exist in the database; that row was dropped (the rest loaded). Add it to the data, then re-run that subject.
- **`NOT JSON ... saved as .json.raw`** in `run`, or a `model error` / timeout (15 min per call): fix the `.json.raw` by hand and rename it to `.json`, or delete it and run again.
- **`exported at prompt version X, the prompt is now Y`**: export again.
- **Loading twice is safe**: deterministic ids, a re-load replaces the same cards.
- Logs of every run (prompt text, raw reply, tokens, cost, `details.source = batch file ...`): table `staging.prompt_run`.

# Set 1 - News & weekly

Prompts, in run order (a later one reads what an earlier one loaded):

| # | prompt | when | what it makes | needs | time / cost per subject* |
|---|---|---|---|---|---|
| 1 | `news` | daily | merges duplicate headlines into stories, gives each a category | news job has fetched candidates | 30 s, $0.10 (per competitor) |
| 2 | `signal` | daily | competitive signal card per news article | news loaded first | 25-35 s, $0.03-0.08 |
| 3 | `tech_article` | daily/weekly | technology overview article from a news article | news loaded | 28 s, $0.08 |
| 4 | `opportunity` | weekly | market opportunity from a demand article | news loaded | 33 s, $0.11 |
| 5 | `tender` | daily | tender extracted from a notice | notices in `staging.market_tender_source` | 36 s, $0.11 |
| 6 | `moment` | weekly | graded moves of one competitor, last 90 days | news + signals loaded | 83 s, $0.26 |
| 7 | `tender_assessment` | weekly | client fit / matched products per tender | `tender` loaded | 15 s, $0.05 |
| 8 | `top_opportunity` | weekly | top tenders, projects before tender, next moves | `tender_assessment` and `opportunity` loaded | 6-30 s, $0.03 |

*From the latest test runs in the local `staging.prompt_run`. No web search in this set. A day with 35 signals is roughly 35 x $0.08 = $3 and 20 minutes.

**Order matters.** `signal` needs the stories `news` writes, `tender_assessment` needs `tender`, `top_opportunity` needs `tender_assessment` and `opportunity`.
So the set is processed prompt by prompt: export, run, **load**, then the next prompt. `auto.sh` does exactly that; with the step-by-step way, load each prompt before you export the next (`--prompt ID`).

## Before you start
1. Tunnel (leave it open): `bash routines/tunnel.sh` (or `powershell -File routines\tunnel.ps1`). One-time setup: `routines/SETUP.md`.
2. **The news job comes first.** It searches for new articles and writes them to the holding table `staging.news_candidate`; the `news` prompt then turns them into stories. Pick the dates since the last run:

       python -m prompts.batch news --competitor all --products --from 2026-10-08 --to 2026-10-15

   `prompts.batch news` is `python -m backend.news` with `KSSL_STAGING_DSN` set to the VPS database for you (add `--db local` for the local one). Same arguments: `--date`, `--limit`, `--dry-run`.
   Article images are saved on this PC under `media/news/`.
3. See what is pending: `python -m prompts.batch check --set set1`

## Way A - automatic (claude CLI), whole set
    bash routines/set1_news_weekly/auto.sh                 # every pending subject, prompt by prompt
    bash routines/set1_news_weekly/auto.sh --limit 3       # a small trial: 3 subjects per prompt
    bash routines/set1_news_weekly/auto.sh --prompt news   # one prompt only

Each prompt: files are written to `routines/set1_news_weekly/work/<today>/`, run through Claude, loaded. One line per subject, e.g.
`signal  0206e0a2 AK-203 rifles made in India to fire  loaded  rows=8 tokens=4081/3617 24.1s $0.0753`.

## Way B - step by step (also the manual paste way)
Do this for each prompt in the table order, one at a time (`news` first):

    bash routines/set1_news_weekly/export.sh --prompt news      # 1. files in work/<today>/
    bash routines/set1_news_weekly/run.sh    --prompt news      # 2. Claude CLI writes <name>.json   (or do it by hand, below)
    bash routines/set1_news_weekly/load.sh   --prompt news      # 3. validate + load into kssl_staging
    # then the same three lines for signal, tech_article, opportunity, tender, moment, tender_assessment, top_opportunity

Options: `export.sh --limit N` (at most N subjects), `--rerun` (also subjects that already ran at this prompt version),
`load.sh --dry-run` (validate only: nothing written, nothing logged, files stay). `DAY=2026-10-16 bash .../load.sh` works on another day's folder.
Without the wrappers: `python -m prompts.batch export --set set1 --prompt news --out routines/set1_news_weekly/work/2026-10-16`, then `python -m prompts.batch run <dir>` and `python -m prompts.batch load <dir>`.

### Manual run (instead of step 2)
For each `work/<date>/<name>.prompt.md`: open it, copy from the line `## SYSTEM` to the end, paste into a new claude.ai chat
(model as in the header comment; no web search needed in this set), and save Claude's whole reply as `<name>.json` in the same folder
(code fences or a sentence around the JSON are fine). Then run step 3. `run.sh` skips files that already have a `.json`.

### 4. Approve
Open the review site (`KSSL_REVIEW_URL` in `.env`) (login in `.env`), check the new cards, **Approve**. The live site the live site (`KSSL_LIVE_URL` in `.env`) shows them after that.

## Folders
    routines/set1_news_weekly/work/<date>/            exported <name>.prompt.md + <name>.meta.json (+ <name>.json after the run)
    routines/set1_news_weekly/work/<date>/loaded/     processed OK (loaded, or skipped by the model; both are logged in staging.prompt_run)
    routines/set1_news_weekly/work/<date>/rejected/   validation failed; <name>.err.txt says why
`<name>` = `<prompt>__<subject key>`. The `work/` folder is gitignored (it holds article text).

## Troubleshooting
- **`open the tunnel first`**: start `routines/tunnel.sh` and keep it open. If it says port 55460 is already open, a tunnel is already running: fine.
- **A file landed in `rejected/`**: read its `.err.txt` (e.g. `output is not JSON`, value not allowed, unresolved name). The run is logged as `rejected`, so the subject is not offered again by default.
  Fix by hand: edit `<name>.json`, move the three files back to `work/<date>/`, run `load.sh` again. Or start over: `export.sh --prompt ID --rerun`, run, load.
- **`NOT exported: DocumentError ... no readable article text`**: the article page is paywalled or blocked; that subject is skipped, the others are exported.
- **`model error` / `NOT JSON ... saved as .json.raw`** in `run`: fix the `.json.raw` by hand and rename it to `.json`, or delete it and run again.
- **`exported at prompt version X, the prompt is now Y`**: the prompt text changed after the export; export again.
- **Loading twice is safe**: ids are deterministic, so a re-load replaces the same cards (shown as "changed" in the review site), no duplicates.
- **The model answered "skipped"** (the article is not a signal/opportunity): normal, logged with the reason, nothing loaded.
- Logs of every run (prompt text, raw reply, tokens, cost, `details.source = batch file ...`): table `staging.prompt_run` in kssl_staging.

# One-time setup for the prompt routines

The routines run on your PC. They read from and write to the **kssl_staging** database on the VPS through an SSH tunnel.
They never write kssl_serving (the live site): only **Approve** in the review site does that.

```
your PC:  prompts.batch  --(ssh tunnel, localhost:55460)-->  VPS: kssl2-db (127.0.0.1:5460) / kssl_staging
          claude CLI (your Claude plan)                         review site: Approve -> kssl_serving -> live site
```

## 1. Python and packages
Python 3.11+ (Git Bash or PowerShell, from the folder `kssl_local`):

    pip install psycopg2-binary pyyaml fastapi

`fastapi` is only imported by the news code (`backend/news.py`), which the prompts use to read article pages.

## 2. Claude CLI
    npm i -g @anthropic-ai/claude-code
    claude            # first start: log in with your Claude account, then exit

Automatic runs (`run`, `auto`) use your **Claude plan** (the same login), not an API key. Check: `claude --version`.
The manual way (paste into claude.ai) needs nothing installed.

## 3. SSH key for the VPS
Put the private key at `~/.ssh/kssl_vps` (Windows: `C:\Users\<you>\.ssh\kssl_vps`). Host and SSH user: `KSSL_VPS_HOST`, `KSSL_VPS_SSH_USER` in `.env`.
On Git Bash/Linux/macOS: `chmod 600 ~/.ssh/kssl_vps`. Windows OpenSSH may complain about permissions: the file must belong to you only.

## 4. The `.env` file
In `kssl_local/` copy `.env.example` to `.env` and fill in the values you were given. **Never commit it** (it is gitignored).
Keys used by the routines:

| Key | Used for |
|---|---|
| `KSSL_VPS_HOST`, `KSSL_VPS_SSH_USER` | the VPS the tunnel connects to (`routines/tunnel.sh` / `tunnel.ps1`) |
| `KSSL_VPS_STAGING_DSN` | connection to kssl_staging on the VPS: must point at `127.0.0.1:55460` (the tunnel) |
| `KSSL_STAGING_DSN` | the LOCAL kssl_staging (only for `--db local` tests; optional) |
| `KSSL_REVIEW_URL`, `KSSL_REVIEW_USER`, `KSSL_REVIEW_PASSWORD` | the review site and its login |
| `KSSL_LIVE_URL` | the live site |

(The other keys, `KSSL_VPS_DB_*`, `KSSL_VPS_SERVING_DSN`, `KSSL_SERVING_DSN`, are for admin work and are not used by the routines.)
Format: `KEY=value`, one per line; quotes around the value are allowed.

## 5. Open the tunnel and test
Open a terminal and leave it open while you work (Ctrl+C closes the tunnel):

    bash routines/tunnel.sh                       # Git Bash
    powershell -File routines\tunnel.ps1          # PowerShell

In a second terminal:

    python -m prompts.batch check --set set1      # lists every prompt of the set and how many subjects are pending
    python -m prompts.batch check --set set2

It prints `database: vps  127.0.0.1:55460/kssl_staging` and a table. If it says `open the tunnel first`, the tunnel is not running.
Add `--db local` to any command to use your local database instead (for tests).

## 6. Page-setup rows (once, on the VPS)
The VPS database copy is older than the local one. Before the first run there, add the page-configuration rows the prompts need
(project stages Concept/Trials/Contract/Production, the Domestic/Export filter, the Technology pillar). The file only inserts rows that are missing, so running it twice is safe:

    python -m prompts.batch sql db/setup/07_page_setup.sql --db vps       # tunnel open

(Alternative with psql: `psql "<the KSSL_VPS_STAGING_DSN value>" -f db/setup/07_page_setup.sql`.)
Locally the same file is applied by `bash db/make_databases.sh`.

## 7. Where the results go
Loaded rows wait in **kssl_staging** until a person approves them:

- Review site: the review site (`KSSL_REVIEW_URL` in `.env`) (user/password in `.env`: `KSSL_REVIEW_USER`, `KSSL_REVIEW_PASSWORD`). Approve moves rows to the live database.
- Live site: the live site (`KSSL_LIVE_URL` in `.env`) (shows only what was approved).

## 8. What to do each time
See `routines/set1_news_weekly/README.md` and `routines/set2_research/README.md`.
Short form: tunnel, then `export`, `run` (or paste by hand), `load`, then Approve in the review site.

## Safety notes
- `load` validates every reply (allowed values, references to ids, quotes against the prompt text) before it writes, and writes only to kssl_staging.
- Credentials are only read from `.env` / the environment; the scripts print the host, port and database name, never the password.
- `--db vps` ignores a `KSSL_STAGING_DSN` left in your shell, so a stale local value can never point a VPS run at the wrong place (and the other way round).
- Exported prompt files contain fetched article text: they live in `routines/<set>/work/` (gitignored).

# Server deployment (beside the product's own stack)

Parallax Analyst runs as one extra container next to the product's `kssl2` Compose stack
(`../../deploy/docker-compose.yml`): it joins the `kssl2_default` network and reads what the live
site reads, so the product's stack is unchanged.

    # on the server, after the product is deployed (deploy/deploy_vps.sh), in <repo>/parallax-agent/deploy
    printf 'PARALLAX_DB_PASSWORD=<the db admin password>\nPARALLAX_PORT=8101\n' > .env   # chmod 600
    cp <model key file> ../.env                                                       # LLM_PROVIDER, OPENROUTER_API_KEY / ANTHROPIC_API_KEY
    docker compose -p kssl2-parallax up -d --build

Open `http://<server>:8101`: the live product with the chat. To serve it on a hostname instead,
drop `ports:` and add Traefik labels as the product's `web` service has them
(`traefik.docker.network=kssl2_default`).

- **Database rights.** On startup the service creates the read-only `analytics` schema of views
  over `serving` and the `parallax_agent` role in `kssl_serving` (idempotent). That needs a login
  with CREATE on the database and CREATEROLE, normally the stack's admin user. To avoid giving it
  that, apply `../adapter/analytics.sql` once by hand as the admin, set `AGENT_ENSURE_ANALYTICS=0`
  and `AGENT_DB_PASSWORD=<a password you set for parallax_agent>`, and connect with a login that
  can `ALTER ROLE parallax_agent PASSWORD` (or use the parallax_agent role itself).
- **What visitors can reach.** Only the API paths the live pages call are forwarded
  (`PRODUCT_API_ALLOW`); the review, trace and news-refresh routes are not.
- **No login** on the chat, as on the live site: anyone with the URL can use it. The spend cap
  (`AGENT_BUDGET_USD`) bounds model cost; `state/spend-baseline.json` keeps it across rebuilds.
- `deploy_vps.sh` ships `git archive` output, so `parallax-agent/` must be committed in the
  deployed ref.

Stop: `docker compose -p kssl2-parallax down`.

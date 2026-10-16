#!/usr/bin/env bash
# ONE-OFF (done 2026-10-16): copy what sits in kssl_frontend's staging / staging_ui schemas (news rows,
# the test competitors + products, fact_source) into kssl_staging. Same schema names on both sides,
# so a data-only dump restores as is. kssl_frontend is only read (it stays as the backup).
# Refuses to run when kssl_staging already holds any row, so it cannot duplicate or overwrite.
#   bash db/setup/move_frontend_staging.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1
PG=(docker exec -i kssl-pg)
BUSY=$("${PG[@]}" psql -U kssl -d kssl_staging -At -c "SELECT count(*) FROM (
  SELECT 1 FROM staging.competitive_competitor UNION ALL SELECT 1 FROM staging.competitive_news_article
  UNION ALL SELECT 1 FROM staging.competitive_product UNION ALL SELECT 1 FROM staging.fact_source) t")
[ "$BUSY" = 0 ] || { echo "kssl_staging already has rows - nothing moved"; exit 1; }
"${PG[@]}" pg_dump -U kssl -d kssl_frontend --data-only --no-owner -n staging -n staging_ui \
  | "${PG[@]}" psql -v ON_ERROR_STOP=1 -q -U kssl -d kssl_staging >/dev/null
for s in staging staging_ui; do
  for db in kssl_frontend kssl_staging; do
    echo "== $db.$s (tables with rows)"
    "${PG[@]}" psql -U kssl -d "$db" -At -c "SELECT table_name || '=' || (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text
      FROM information_schema.tables WHERE table_schema = '$s' AND table_type = 'BASE TABLE' ORDER BY 1" | grep -v '=0$' || true
  done
done

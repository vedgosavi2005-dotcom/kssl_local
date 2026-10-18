#!/usr/bin/env bash
# Throwaway staging + serving pair filled with the FULL fictional seed (db/test_seed_full/*.sql, every table).
#   bash db/make_test_pair.sh [--approve-all]
#     1. drops + recreates kssl_test_staging and kssl_test_serving (only these two names, never the real DBs)
#     2. builds both with db/make_databases.sh (same schema, migrations and setup as the real pair)
#     3. loads db/test_seed_full/*.sql into kssl_test_staging in name order
#     4. prints a coverage table (rows per table of staging + staging_ui) and a FAIL line for every empty table
#     5. --approve-all: copies every staging.X -> serving.X and staging_ui.X -> ui.X in kssl_test_serving, in ONE
#        transaction with SET LOCAL kssl.approve = 'on' (as if every card and setup table had been approved)
# Without --approve-all the serving DB stays empty, so the review backend shows every card as "new".
# Only the two databases named above are ever dropped; the real kssl_staging / kssl_serving are never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

# KSSL_TEST_TAG (optional, letters/digits only, e.g. "a") gives a private pair kssl_test_staging_a / kssl_test_serving_a,
# so two people can run the script at the same time. Without it the names are kssl_test_staging / kssl_test_serving.
TAG="${KSSL_TEST_TAG:-}"
case "$TAG" in *[!a-zA-Z0-9]*) echo "refusing: KSSL_TEST_TAG must be letters/digits only"; exit 1;; esac
STG="kssl_test_staging${TAG:+_$TAG}"
SRV="kssl_test_serving${TAG:+_$TAG}"
case "$STG$SRV" in kssl_test_staging*kssl_test_serving*) ;; *) echo "refusing: database names must be kssl_test_staging* / kssl_test_serving*"; exit 1;; esac

APPROVE=0
for a in "$@"; do
    case "$a" in
        --approve-all) APPROVE=1;;
        *) echo "usage: bash db/make_test_pair.sh [--approve-all]"; exit 1;;
    esac
done

PSQL=(docker exec -i kssl-pg psql -v ON_ERROR_STOP=1 -q -U kssl)

echo "== recreating $STG and $SRV"
for db in "$STG" "$SRV"; do
    "${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS $db WITH (FORCE)"
done
bash db/make_databases.sh "$STG" "$SRV"

echo "== loading db/test_seed_full/*.sql into $STG"
for f in db/test_seed_full/*.sql; do
    [ -e "$f" ] || { echo "no seed files found"; exit 1; }
    echo "seed $f"
    "${PSQL[@]}" -d "$STG" < "$f"
done

# rows per table: "schema.table count" lines for one database and its two schemas
counts() {  # counts <db> <schema> <schema>
    "${PSQL[@]}" -d "$1" -At -F' ' -c "
        SELECT table_schema || '.' || table_name,
               (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE' AND table_schema IN ('$2', '$3') ORDER BY 1"
}

if [ "$APPROVE" = 1 ]; then
    echo "== approve-all: copying staging -> serving and staging_ui -> ui in $SRV (one transaction)"
    # runs inside the container so each table streams psql COPY ... TO STDOUT into one psql COPY ... FROM STDIN script
    SCRIPT=$(cat <<'INNER'
S=__STG__; V=__SRV__
{
    echo "BEGIN;"
    echo "SET LOCAL kssl.approve = 'on';"
    for pair in serving:staging ui:staging_ui; do
        live=${pair%%:*}; st=${pair##*:}
        for t in $(psql -U kssl -d $V -At -c "SELECT tablename FROM pg_tables WHERE schemaname = '$live' ORDER BY 1"); do
            [ "$(psql -U kssl -d $S -At -c "SELECT to_regclass('$st.$t') IS NOT NULL")" = t ] || continue
            cols=$(psql -U kssl -d $V -At -c "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema = '$live' AND table_name = '$t'")
            echo "DELETE FROM $live.$t;"
            echo "COPY $live.$t ($cols) FROM STDIN;"
            psql -U kssl -d $S -c "COPY (SELECT $cols FROM $st.$t) TO STDOUT"
            echo '\.'
        done
    done
    echo "COMMIT;"
} | psql -v ON_ERROR_STOP=1 -q -U kssl -d $V
INNER
)
    SCRIPT=${SCRIPT//__STG__/$STG}; SCRIPT=${SCRIPT//__SRV__/$SRV}
    docker exec kssl-pg bash -c "$SCRIPT"
fi

echo
echo "== coverage: rows per table"
STAGED=$(counts "$STG" staging staging_ui)
if [ "$APPROVE" = 1 ]; then
    LIVE=$(counts "$SRV" serving ui | sed -e 's/^serving\./staging./' -e 's/^ui\./staging_ui./')
else
    LIVE=""
fi
FAILS=0
printf '%-62s %8s %8s\n' table staged live
while read -r name n; do
    [ -n "$name" ] || continue
    l=$(printf '%s\n' "$LIVE" | awk -v k="$name" '$1 == k {print $2}')
    printf '%-62s %8s %8s\n' "$name" "$n" "${l:--}"
    if [ "$n" = 0 ]; then echo "FAIL: $name has 0 rows"; FAILS=$((FAILS + 1)); fi
    if [ "$APPROVE" = 1 ] && [ -n "$l" ] && [ "$l" != "$n" ] && [ "$name" != staging.review_decision ]; then
        echo "FAIL: $name staged $n rows but live has $l"; FAILS=$((FAILS + 1))
    fi
done <<< "$STAGED"
echo
if [ "$FAILS" = 0 ]; then echo "coverage OK: every table of staging and staging_ui has rows"; else echo "$FAILS FAIL line(s) above"; fi

cat <<EOF

View it (run from the repo root, ports 8610/8611 are reserved for these test backends):
  live    (serving DB)  KSSL_DSN="host=127.0.0.1 port=55432 dbname=$SRV user=kssl password=kssl" python -m uvicorn backend.app:app --port 8610
  review  (staging DB)  KSSL_VIEW=review KSSL_STAGING_DSN="host=127.0.0.1 port=55432 dbname=$STG user=kssl password=kssl" KSSL_SERVING_DSN="host=127.0.0.1 port=55432 dbname=$SRV user=kssl password=kssl" python -m uvicorn backend.app:app --port 8611
  then: curl http://127.0.0.1:8610/api/dataset   |   curl http://127.0.0.1:8611/api/dataset
EOF
[ "$FAILS" = 0 ]

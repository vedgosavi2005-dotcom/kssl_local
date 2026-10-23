#!/usr/bin/env bash
# Publish everything: staging -> serving and staging_ui -> ui, every table, in ONE transaction (as if every card and
# every setup table had been approved, rejected ones included), then clear staging.review_decision.
#   bash db/publish_all.sh local      (kssl-pg: kssl_staging -> kssl_serving)
#   bash db/publish_all.sh vps        (kssl2-db on the VPS, same databases)
# Review-only content (KSSL's own entry, risk score / why-basis, prompt stats) is copied too: the live API never sends
# it (backend/areas/*._review). Take a pg_dump of serving first; this replaces every serving / ui table it copies.
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET="${1:-}"
# local test run only: KSSL_PUBLISH_TEST=<tag> publishes kssl_test_staging_<tag> -> kssl_test_serving_<tag> instead
T="${KSSL_PUBLISH_TEST:-}"; case "$T" in *[!a-zA-Z0-9]*) echo "refusing: bad KSSL_PUBLISH_TEST"; exit 1;; esac
SCRIPT=$(cat <<'INNER'
set -eo pipefail; S=__S__; V=__V__; U=__USER__
{
    echo "BEGIN;"
    echo "SET LOCAL kssl.approve = 'on';"
    for pair in serving:staging ui:staging_ui; do
        live=${pair%%:*}; st=${pair##*:}
        for t in $(psql -U $U -d $V -At -c "SELECT tablename FROM pg_tables WHERE schemaname = '$live' ORDER BY 1"); do
            [ "$(psql -U $U -d $S -At -c "SELECT to_regclass('$st.$t') IS NOT NULL")" = t ] || continue
            # the columns both sides have: a serving-only column (an older migration on that server) is left NULL / default
            stc=$(psql -U $U -d $S -At -c "SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_schema = '$st' AND table_name = '$t'")
            cols=$(psql -U $U -d $V -At -c "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema = '$live' AND table_name = '$t' AND column_name = ANY(string_to_array('$stc', ','))")
            echo "DELETE FROM $live.$t;"
            echo "COPY $live.$t ($cols) FROM STDIN;"
            psql -U $U -d $S -c "COPY (SELECT $cols FROM $st.$t) TO STDOUT"
            echo '\.'
        done
    done
    echo "COMMIT;"
} | psql -v ON_ERROR_STOP=1 -q -U $U -d $V
psql -v ON_ERROR_STOP=1 -q -U $U -d $S -c "DELETE FROM staging.review_decision"
echo "published: $(psql -U $U -d $V -At -c "SELECT count(*) FROM pg_tables WHERE schemaname IN ('serving','ui')") live tables"
INNER
)
case "$TARGET" in
  local)
    if [ -n "$T" ]; then SCRIPT=${SCRIPT//__S__/kssl_test_staging_$T}; SCRIPT=${SCRIPT//__V__/kssl_test_serving_$T}
    else SCRIPT=${SCRIPT//__S__/kssl_staging}; SCRIPT=${SCRIPT//__V__/kssl_serving}; fi
    docker exec kssl-pg bash -c "${SCRIPT//__USER__/kssl}" ;;
  vps)
    SCRIPT=${SCRIPT//__S__/kssl_staging}; SCRIPT=${SCRIPT//__V__/kssl_serving}
    envval() { sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'\r"; }
    H="${KSSL_VPS_HOST:-$(envval KSSL_VPS_HOST)}"; U="${KSSL_VPS_SSH_USER:-$(envval KSSL_VPS_SSH_USER)}"
    [ -n "$H" ] && [ -n "$U" ] || { echo "set KSSL_VPS_HOST and KSSL_VPS_SSH_USER in .env"; exit 1; }
    printf '%s' "${SCRIPT//__USER__/kssl_admin}" | ssh -i "${KSSL_SSH_KEY:-$HOME/.ssh/kssl_vps}" -o ConnectTimeout=20 -o BatchMode=yes "$U@$H" 'docker exec -i kssl2-db bash -s' ;;
  *) echo "usage: bash db/publish_all.sh local|vps"; exit 1 ;;
esac

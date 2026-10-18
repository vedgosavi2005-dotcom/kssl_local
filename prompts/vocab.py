"""The loader vocabulary: what a `loader:` value in a prompt file can say (see prompts/FORMAT.md).

A loader value is a TOKEN (a string such as `new_id`, `subject.display_name`, `copy_of_buyer_name`),
a TEMPLATE ("{subject.display_name} <-> {partner_name}"), a literal (true / false / number / null),
or a MAP ({behind: "...", ahead: "..."}: keyed by whichever column of the row or its parents holds one
of the keys). `check_token` validates a spec when it is parsed; `evaluate` computes the value for one
row at load time. Rows are prompts.loader.Row objects, `L` the Loader (duck-typed here).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from backend.sources import host_of

UNSET = object()          # "leave this column alone": derive.* fills it later, keep* keeps the stored value
STABLE_RANK_ORIGIN = date(2100, 1, 1)

# ref name -> (table, id column, [name columns], scope column)   (all in schema staging)
REFS = {
    "ref_competitor": ("competitive_competitor", "competitor_id", ["display_name", "short_name", "legal_name"], None),
    "ref_product": ("competitive_product", "product_id", ["product_name"], "competitor_id"),
    "ref_client_product": ("client_product", "client_product_id", ["product_name"], None),
    "ref_category": ("technology_category", "category_id", ["category_name"], None),
    "ref_tender": ("market_tender", "tender_id", ["title", "notice_reference", "tender_number"], None),
    "ref_opportunity": ("market_opportunity", "opportunity_id", ["title"], None),
    "ref_location": ("competitive_geo_location", "location_id", ["country_name"], None),
    "ref_innovation": ("technology_innovation", "innovation_id", ["title"], None),
    "ref_signal": ("competitive_signal", "signal_id", ["title"], "company_id"),            # a moment points at the signal it rolls up (scope: the subject competitor)
    "ref_partnership": ("competitive_partnership", "relationship_id", ["partner_name"], "competitor_id"),   # a synthesis weakness traces to the ties of the subject competitor
    "ref_client_spec": ("client_product_specification", "specification_id", ["spec_name"], "client_product_id"),
    "ref_competitor_spec": ("competitive_product_specification", "spec_id", ["spec_label"], "product_id"),
}
SPECIAL_REFS = {"ref_filing"}        # resolved by the loader from the subject (batch handles F001...)
ID_COLUMNS = {v[1]: (v[0], v[2][0]) for v in REFS.values() if v[2]}      # category_id -> (table, name column)

RESERVED_SUFFIXES = ("_desc",)


class NoValue(Exception):
    """The token cannot be computed for this row (the row is dropped with this reason)."""


# ---- helpers on Row objects ---------------------------------------------------------------------------

def tail_match(table: str, prefix: str) -> bool:
    return table == prefix or table.endswith("_" + prefix)


def relatives(row) -> list:
    """Rows a token may look at: ancestors, context rows (a driver's source row), siblings, children."""
    out = [v for v in row.ctx.values() if hasattr(v, "table")]          # a driver's source row first
    p = row.parent
    while p is not None:
        out.append(p)
        p = p.parent
    if row.parent is not None:
        out += [s for s in row.parent.children if s is not row]
    out += list(row.children)
    return out


def find_col(row, name: str):
    """Value of a column by bare name: this row, then its relatives. (found, value)."""
    if row.has(name):
        return True, row.get(name)
    for r in relatives(row):
        if r.has(name):
            return True, r.get(name)
    return False, None


def find_prefixed(row, x: str):
    """copy_of_<prefix>_<col>: <col> of the related row whose table ends with <prefix>."""
    for i, ch in enumerate(x):
        if ch != "_":
            continue
        prefix, col = x[:i], x[i + 1:]
        for r in relatives(row):
            if tail_match(r.table, prefix) and r.has(col):
                return True, r.get(col)
        got = row.resolved.get("ref_" + prefix)             # copy_of_tender_status on a row that refers to a tender
        if got is not None and col in got["row"]:
            return True, got["row"][col]
    return False, None


def as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return date.fromisoformat(v.strip())
    return None


def slug(s) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def plain_number(v):
    if v is None:
        return None
    s = str(v).strip()
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", s):
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


# ---- token handlers -------------------------------------------------------------------------------------
# every handler: (match, row, L, col) -> value | UNSET ; raises NoValue

def h_new_id(m, row, L, col):
    return L.new_id(row, col)


def h_new_id_stable(m, row, L, col):
    """The same category + title is the same record whichever document or run found it (global requirements: a re-found requirement is
    updated, not duplicated). Falls back to the run's own id when the row has no title."""
    title = row.get("title")
    if not title:
        return L.new_id(row, col)
    cat = row.get("category")
    return L.stable_id(row.table, col, f"{' '.join(str(cat or '').casefold().split())}|{' '.join(str(title).casefold().split())}")


def h_new_id_or_ref(m, row, L, col):
    ref = "ref_" + m.group(1)
    got = row.resolved.get(ref)
    if got is not None:
        row.mode = "extend"                         # an existing record is extended, not replaced
        return got["id"]
    return L.new_id(row, col)


def h_parent_id(m, row, L, col):
    if row.parent is None:
        raise NoValue("parent_id on a top-level row")
    return row.parent.get(row.parent.key_col)


def h_index(m, row, L, col):
    return row.pos + 1


def h_run_time(m, row, L, col):
    return L.now


def h_run_date(m, row, L, col):
    return L.today


def h_subject(m, row, L, col):
    name = m.group(1)
    role = L.subject.get("company_role")
    if name == "subject_id_when_competitor":
        return L.subject.get("subject_id") if role == "competitor" else None
    if name == "subject_id_when_client":
        return L.subject.get("subject_id") if role == "client" else None
    if name not in L.subject:
        raise NoValue(f"subject has no column '{name}'")
    return L.subject[name]


def h_transient(m, row, L, col):
    name = m.group(1)
    for r in [row, *relatives(row)]:
        if name in r.transient:
            return r.transient[name]
    return None


def h_host(m, row, L, col):
    url = row.get("source_url") if "source" in m.group(0) else (row.get("url") or row.get("source_url"))
    return host_of(url) if url else None


def h_article_image(m, row, L, col):
    """competitive_signal.thumbnail_url: the subject's image_url, else the image stored for the same article url, else the
    article page's og:image (backend/news.py parse_page). Null when none is found; never an error."""
    return L.article_image()


def h_article_published(m, row, L, col):
    """competitive_signal.published_date: the article's publication date (source_document.published_at for its url, else the
    subject's published_date). Null when not known; never an error."""
    return L.article_published()


def h_from_ui(m, row, L, col):
    table, c = m.group(1), m.group(2)
    ui = row.ctx.get("ui")
    if isinstance(ui, dict) and ui.get("_table") == table:
        return ui.get(c)
    return L.ui_value(table, c)


def h_derive(m, row, L, col):
    return UNSET


def h_keep(m, row, L, col):
    return UNSET


def h_constant(m, row, L, col):
    return m.group(1)


def h_same_as(m, row, L, col):
    return find_col(row, m.group(1))[1]


def h_rank_desc(m, row, L, col):
    d = as_date(row.get(m.group(1))) or L.today
    return (STABLE_RANK_ORIGIN - d).days


def h_rank_country(m, row, L, col):
    return L.alpha_rank(row)


def h_count_children(m, row, L, col):
    return len(row.children)


def h_count_evidence(m, row, L, col):
    return sum(tail_match(c.table, "evidence") for c in row.children)


def h_evidence_exists(m, row, L, col):
    return any(tail_match(c.table, "evidence") for c in row.children)


def h_count_partners(m, row, L, col):
    L.post.append(("partner_count", row))
    return UNSET


def h_join_names(m, row, L, col):
    names = [c.get("product_name") for c in row.children if c.has("product_name") and c.get("product_name")]
    return ", ".join(dict.fromkeys(str(n) for n in names)) or None


def h_latest_timeline(m, row, L, col):
    best = None
    for c in row.children:
        if not tail_match(c.table, "timeline"):
            continue
        d = as_date(c.get("event_date"))
        if d is None or c.get("is_expected") is True:
            continue
        if best is None or d > best[0]:
            best = (d, c.get("event_title"))
    if best is None:
        return None
    return best[1] if m.group(1) == "title" else best[0]


def h_stage_eq(m, row, L, col):
    return row.parent is not None and row.get("stage_name") == row.parent.get("stage")


def h_status_open(m, row, L, col):
    return str(row.get("status") or "").lower() == "open"


def h_name_of_id(m, row, L, col):
    return L.name_of(m.group(1), row.get(m.group(1)))


def h_resolved(m, row, L, col):
    ref, what = m.group(1), m.group(2)
    got = row.resolved.get(ref)
    if got is None:                                  # may be resolved on an ancestor (a match's geo product...)
        for r in relatives(row):
            if ref in r.resolved:
                got = r.resolved[ref]
                break
    if got is None:
        return None
    table, idc, ncols, _ = REFS[ref]
    if what == "id":
        return got["id"]
    if what == "name":
        return got["row"].get(ncols[0])
    return got["row"].get(what)


# spec copies: column of the loader target decides which field of the spec row is meant
def _spec_field(spec: dict, target: str, client: bool):
    if target in ("unit", "spec_group"):
        return spec.get(target)
    numeric = target.endswith("numeric")
    if client:
        if numeric:
            return spec.get("value_numeric")
        t = spec.get("value_text")
        return t if t not in (None, "") else (None if spec.get("value_numeric") is None else format(spec["value_numeric"].normalize(), "f"))
    if numeric:
        return plain_number(spec.get("spec_value"))
    return spec.get("spec_value")


def h_copy_client_spec(m, row, L, col):
    got = row.resolved.get("ref_client_spec")
    variant = m.group(1) or ""
    if got is not None:
        return _spec_field(got["row"], col, True)
    if variant == "_else_competitor_spec":
        other = row.resolved.get("ref_competitor_spec")
        return _spec_field(other["row"], col, False) if other else None
    return None


def h_copy_comp_spec(m, row, L, col):
    got = row.resolved.get("ref_competitor_spec")
    return _spec_field(got["row"], col, False) if got is not None else None


def h_parse_number_comp(m, row, L, col):
    got = row.resolved.get("ref_competitor_spec")
    return plain_number(got["row"].get("spec_value")) if got is not None else None


def h_copy_of_ref_spec(m, row, L, col):
    got = row.resolved.get("ref_client_spec")
    return got["row"].get("spec_name") if got is not None else None


def h_copy_of(m, row, L, col):
    x = m.group(1)
    if x != col:                                       # copy_of_display_name filling display_name: look at the source row
        found, v = find_col(row, x)
        if found:
            return v
    else:
        for r in relatives(row):
            if r.has(x):
                return r.get(x)
    found, v = find_prefixed(row, x)
    return v if found else None


def h_uuid5_of(m, row, L, col):
    return L.casefold_uuid(m.group(1), row.get(m.group(1)))


def h_country_ref(m, row, L, col):
    suffix = m.group(1) or ""
    if suffix == "_of_opportunity_country_code":
        code = L.name_of_col("market_opportunity", "opportunity_id", row.get("opportunity_id"), "country_code")
        c = L.country(code)
        return c["country_name"] if c else None
    if suffix == "_of_country":
        src = next((r.transient["country"] for r in [row, *relatives(row)] if "country" in r.transient), None)
    else:
        src = row.get("country_name") or (row.ctx.get("ref_name") if row.ctx else None)
    c = L.country(src)
    if c is None:
        if src:
            L.warn(f"{row.table}.{col}: country '{src}' is not in staging.country_reference")
        return None
    return {"country_code": c["iso2"], "latitude": c["latitude"], "longitude": c["longitude"],
            "region_name": c["region_name"], "country_name": c["country_name"]}.get(col, UNSET)


def h_due_text(m, row, L, col):
    d = as_date(row.get("due_date"))
    return f"{d.day} {d:%b} {d.year}" if d else None


def h_label_of(m, row, L, col):
    v = row.get(m.group(1))
    return str(v)[:1].upper() + str(v)[1:] if v else None


def h_developer(m, row, L, col):
    comps = [c for c in row.children if tail_match(c.table, "company")]
    pick = next((c for c in comps if str(c.get("relationship") or "").lower() == "developer"), None)   # no developer named: none, not the first
    return pick.get("company_id") if pick else None


def h_competitor_or_third(m, row, L, col):
    return "competitor" if "ref_competitor" in row.resolved else "third_party"


def h_find_or_create(m, row, L, col):
    return L.find_or_create(row, "technology_" + m.group(1), m.group(2))


def h_single_source(m, row, L, col):
    return "official" if str(row.get("source_type") or "").lower() == "official" else "single_source"


def h_sibling_source(m, row, L, col):
    sib = next((s for s in (row.parent.children if row.parent else []) if s is not row and tail_match(s.table, "source")), None)
    return sib.get("source_id") if sib else None


def h_ctx_url(m, row, L, col):
    return row.ctx.get("url")


def h_slug_id(m, row, L, col):
    return f"{row.get('category_id')}-{slug(row.get('title'))}"


def h_pillar(m, row, L, col):
    return L.pillar(m.group(0).endswith("name"))


def h_from_ref_name(m, row, L, col):
    return row.ctx.get("ref_name")


def h_competitor_products(m, row, L, col):
    got = row.resolved.get("ref_competitor")
    return L.competitor_products_in_category(got["id"] if got else None)


FIT_ORDER = {"strong": 0, "partial": 1, "weak": 2}


def h_sort_fit(m, row, L, col):
    sibs = [s for s in (row.parent.children if row.parent else [row]) if s.table == row.table]
    order = sorted(sibs, key=lambda s: (FIT_ORDER.get(str(s.get("fit_label") or "").lower(), 3), s.pos))
    return order.index(row) + 1


def h_matched(m, row, L, col):
    return "matched" if any(tail_match(c.table, "product_match") for c in row.children) else "no_match"


def h_bare(m, row, L, col):
    found, v = find_col(row, m.group(0))
    if found:
        return v
    found, v = find_prefixed(row, m.group(0))
    if found:
        return v
    raise NoValue(f"'{m.group(0)}' names no column of this row or its relatives")


# order matters: the first match wins; the last entry is the bare-column fallback
TOKENS = [
    (r"new_id_stable_by_category_and_title", h_new_id_stable),
    (r"new_id(?:_if_missing)?", h_new_id),
    (r"new_id_or_ref_(\w+)", h_new_id_or_ref),
    (r"parent_id", h_parent_id),
    (r"index|index_plus_1_of_output_order", h_index),
    (r"now|run_time", h_run_time),
    (r"run_date", h_run_date),
    (r"subject\.(\w+)", h_subject),
    (r"transient\.(\w+)", h_transient),
    (r"host_of_(?:source_)?url", h_host),
    (r"article_image_url", h_article_image),
    (r"article_published_date", h_article_published),
    (r"from_ui\.(\w+)\.(\w+)", h_from_ui),
    (r"from_ref_(\w+)", h_from_ref_name),
    (r"derive\.(\w+)", h_derive),
    (r"keep|keep_stub_value", h_keep),
    (r"constant_(\w+)", h_constant),
    (r"same_as_(\w+)", h_same_as),
    (r"rank_by_country", h_rank_country),
    (r"rank_by_(\w+?)_desc", h_rank_desc),
    (r"count_children", h_count_children),
    (r"count_evidence_cards", h_count_evidence),
    (r"true_when_evidence_exists", h_evidence_exists),
    (r"count_partners_of_competitor", h_count_partners),
    (r"join_child_product_names", h_join_names),
    (r"(title|date)_of_latest_past_timeline_event", h_latest_timeline),
    (r"stage_name_equals_project_stage", h_stage_eq),
    (r"status_is_open", h_status_open),
    (r"(?:name|title)_of_(\w+_id)", h_name_of_id),
    (r"resolved_(" + "|".join(sorted(REFS, key=len, reverse=True)) + r")_(\w+)", h_resolved),
    (r"copy_from_client_spec(_else_none|_else_competitor_spec)?", h_copy_client_spec),
    (r"copy_from_competitor_spec", h_copy_comp_spec),
    (r"parse_plain_number_of_competitor_spec_value_else_null", h_parse_number_comp),
    (r"copy_of_ref_client_spec", h_copy_of_ref_spec),
    (r"copy_of_(\w+)", h_copy_of),
    (r"uuid5_of_casefolded_(\w+)", h_uuid5_of),
    (r"country_reference_table(_of_\w+)?", h_country_ref),
    (r"due_date_formatted_as_d_mon_yyyy", h_due_text),
    (r"label_of_(\w+)", h_label_of),
    (r"company_id_of_the_developer_row", h_developer),
    (r"competitor_when_ref_competitor_resolves_else_third_party", h_competitor_or_third),
    (r"id_of_technology_(source|company)_found_or_created_by_(\w+)", h_find_or_create),
    (r"single_source_unless_publisher_is_official", h_single_source),
    (r"sibling_source_id", h_sibling_source),
    (r"distinct_cited_spec_source_url", h_ctx_url),
    (r"category_id_dash_slug_of_title", h_slug_id),
    (r"technology_pillar_(?:id|name)", h_pillar),
    (r"names_of_that_competitors_products_in_the_category", h_competitor_products),
    (r"sort_by_fit_label_strong_partial_weak_then_output_order", h_sort_fit),
    (r"matched_when_a_product_match_exists_else_no_match", h_matched),
]
COMPILED = [(re.compile(p + r"\Z"), h) for p, h in TOKENS]
BARE = re.compile(r"[a-z][a-z0-9_]*\Z")
TEMPLATE_PART = re.compile(r"\{([^{}]+)\}")


def match(tok: str):
    for rx, h in COMPILED:
        m = rx.match(tok)
        if m:
            return m, h
    if BARE.match(tok):
        return BARE.match(tok), h_bare
    return None, None


def check_token(where: str, col: str, v, literal_ok: bool = False) -> None:
    """Spec-time check of one loader value. Raises ValueError for a token nobody implements."""
    if v is None or isinstance(v, (bool, int, float)):
        return
    if isinstance(v, dict):
        return
    if not isinstance(v, str):
        raise ValueError(f"{where}.{col}: loader value {v!r} is not a token")
    if "{" in v:                         # template ("{x}") or placeholder text ("{{client.name}}")
        return
    m, _ = match(v)
    if m is None and not literal_ok:
        raise ValueError(f"{where}.{col}: unknown loader token '{v}' (see prompts/FORMAT.md)")


def render_template(tpl: str, row, L) -> str | None:
    """"{subject.display_name} <-> {partner_name}" / "{year of as_of_date}" / "{geo product_name}"."""
    def part(m):
        x = m.group(1).strip()
        if x.startswith("subject."):
            v = L.subject.get(x[8:])
        elif x.startswith("year of "):
            d = as_date(find_col(row, x[8:].strip())[1])
            v = d.year if d else None
        else:
            v = find_col(row, x.split()[-1])[1]
        return "" if v is None else str(v)

    out = TEMPLATE_PART.sub(part, tpl)
    segs = [s for s in re.split(r"\s+-\s+", out) if s.strip()]
    return " - ".join(segs) if " - " in tpl else out


def evaluate(v, row, L, col: str):
    """Value of one loader item for `row` (UNSET = leave the column alone)."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, dict):
        for r in [row, *relatives(row)]:
            for val in list(r.cols.values()) + list(r.transient.values()):
                if isinstance(val, str) and val in v:
                    return L.fill_text(str(v[val]))
        return None
    if "{{" in v:
        return L.fill_text(v)
    if "{" in v:
        return render_template(v, row, L)
    m, h = match(v)
    if m is None:
        return v                                        # a literal (rows: section_code: background)
    if h is h_bare and row.literal_ok:
        return v                                        # fixed rows: a plain word is text (section_code: whats_new)
    return h(m, row, L, col)

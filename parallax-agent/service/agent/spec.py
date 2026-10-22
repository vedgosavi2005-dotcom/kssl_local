"""The view spec: the contract between the UI agent and the canvas.

The UI agent fills VIEW_SCHEMA (structured output, so the JSON is always well-formed).
validate() then checks it against the actual result sets -- a widget naming a column that
does not exist is dropped, not rendered as an empty chart -- and hydrate() attaches the
rows. The frontend never receives a number the model typed; every value in a chart is
read from a result set by column name."""

import time
import uuid

from .pages import PAGES

WIDGET_TYPES = ["kpi", "bar", "line", "area", "donut", "scatter", "heatmap", "table", "comparison", "text",
                "treemap", "sankey", "network"]
AGGREGATES = ["sum", "avg", "count", "min", "max", "none"]
FORMATS = ["number", "usd", "percent", "kva", "kw", "liters_per_hour", "kg", "text"]
CLICK_ACTIONS = ["none", "filter", "ask", "navigate"]

_S = {"type": "string"}
_SA = {"type": "array", "items": {"type": "string"}}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


VIEW_SCHEMA = _obj({
    "title": _S,
    "subtitle": _S,
    "summary": _S,
    "widgets": {"type": "array", "items": _obj({
        "type": {"type": "string", "enum": WIDGET_TYPES},
        "title": _S,
        "subtitle": _S,
        "result_id": _S,
        "width": {"type": "string", "enum": ["full", "half", "third"]},
        "x": _S,
        "y": _SA,
        "series": _S,
        "label": _S,
        "size": _S,
        "aggregate": {"type": "string", "enum": AGGREGATES},
        "orientation": {"type": "string", "enum": ["vertical", "horizontal"]},
        "stacked": {"type": "boolean"},
        "sort": {"type": "string", "enum": ["value_desc", "value_asc", "x_asc", "none"]},
        "limit": {"type": "integer"},
        "format": {"type": "string", "enum": FORMATS},
        "highlight": _S,
        "filter_field": _S,
        "filter_value": _S,
        "columns": _SA,
        "kpis": {"type": "array", "items": _obj({
            "label": _S, "result_id": _S, "field": _S,
            "aggregate": {"type": "string", "enum": AGGREGATES},
            "format": {"type": "string", "enum": FORMATS}, "note": _S,
            "filter_field": _S, "filter_value": _S,
        })},
        "text": _S,
        "click": _obj({
            "action": {"type": "string", "enum": CLICK_ACTIONS},
            "field": _S, "question": _S, "pillar": _S, "view": _S, "payload_key": _S,
        }),
    })},
    "filters": {"type": "array", "items": _obj({"field": _S, "label": _S, "default": _S})},
    "assumptions": _SA,
    "caveats": _SA,
    "followups": _SA,
})

_CHARTS_NEEDING_Y = {"bar", "line", "area", "donut", "scatter", "heatmap", "comparison"}
# two categorical columns (source -> target / parent -> child); y is an optional weight
_PAIR_CHARTS = {"treemap", "sankey", "network"}


def validate(spec: dict, results: dict, allowed_ids) -> tuple:
    """Return (clean_spec, warnings). `results` maps result_id -> ResultSet."""
    warnings = []
    allowed = [rid for rid in allowed_ids if rid in results]
    widgets = []

    def resolve_rid(rid):
        if rid in allowed:
            return rid
        if len(allowed) == 1:  # a single-result view: the intent is unambiguous
            return allowed[0]
        return None

    for i, w in enumerate(spec.get("widgets") or []):
        wtype = w.get("type")
        label = f"widget {i + 1} ({wtype} '{w.get('title', '')}')"
        if wtype not in WIDGET_TYPES:
            warnings.append(f"{label}: unknown type")
            continue
        if wtype == "text":
            if (w.get("text") or "").strip():
                widgets.append(_defaults(w))
            continue
        if wtype == "kpi":
            kpis = []
            for k in w.get("kpis") or []:
                rid = resolve_rid(k.get("result_id"))
                rs = results.get(rid) if rid else None
                if not rs:
                    warnings.append(f"{label}: kpi '{k.get('label')}' has unknown result")
                    continue
                field = k.get("field") or ""
                if field and field not in rs.column_names():
                    warnings.append(f"{label}: kpi field '{field}' not in {rid}")
                    continue
                if not field and k.get("aggregate") != "count":
                    warnings.append(f"{label}: kpi '{k.get('label')}' has no field")
                    continue
                ff = k.get("filter_field") or ""
                if ff and ff not in rs.column_names():
                    warnings.append(f"{label}: kpi filter '{ff}' not in {rid}; tile dropped")
                    continue
                kpis.append({**k, "result_id": rid, "filter_field": ff,
                             "filter_value": str(k.get("filter_value") or "") if ff else ""})
            if kpis:
                widgets.append(_defaults({**w, "kpis": kpis, "result_id": kpis[0]["result_id"]}))
            continue

        rid = resolve_rid(w.get("result_id"))
        rs = results.get(rid) if rid else None
        if not rs:
            warnings.append(f"{label}: unknown result_id '{w.get('result_id')}'")
            continue
        cols = rs.column_names()
        w = {**w, "result_id": rid}
        # a widget showing a subset of its result (one segment, one company)
        if w.get("filter_field") and w["filter_field"] not in cols:
            warnings.append(f"{label}: unknown filter_field '{w['filter_field']}'; widget dropped")
            continue
        if not w.get("filter_field"):
            w["filter_value"] = ""
        # optional single-column fields: blank out what does not exist
        for f in ("series", "label", "size"):
            if w.get(f) and w[f] not in cols:
                warnings.append(f"{label}: dropped unknown {f} '{w[f]}'")
                w[f] = ""
        if wtype == "table":
            picked = [c for c in (w.get("columns") or []) if c in cols]
            w["columns"] = picked or cols
        else:
            if w.get("x") not in cols:
                warnings.append(f"{label}: x '{w.get('x')}' not in {rid}")
                continue
            ys = [y for y in (w.get("y") or []) if y in cols]
            numeric_ys = [y for y in ys if rs.column_type(y) == "number"]
            if wtype in _PAIR_CHARTS:
                if wtype != "treemap" and not w.get("series"):
                    warnings.append(f"{label}: {wtype} needs a target column in series")
                    continue
                if not numeric_ys and w.get("aggregate") not in ("count", "sum"):
                    w["aggregate"] = "count"
            if wtype in _CHARTS_NEEDING_Y and not numeric_ys and w.get("aggregate") != "count":
                warnings.append(f"{label}: no numeric y column")
                continue
            w["y"] = numeric_ys
            if wtype == "scatter" and rs.column_type(w["x"]) != "number":
                warnings.append(f"{label}: scatter x must be numeric")
                continue
            if wtype == "comparison" and len(numeric_ys) < 2:
                warnings.append(f"{label}: comparison needs two numeric columns")
                continue
        click = dict(w.get("click") or {})
        if click.get("field") in ("x", "series", "label"):  # the encoding's name, not the column's
            click["field"] = w.get(click["field"]) or ""
        w["click"] = _clean_click(click, cols, warnings, label)
        widgets.append(_defaults(w))

    if not widgets:
        # never send an empty canvas: fall back to the data itself
        warnings.append("no valid widgets; falling back to tables")
        widgets = [_defaults({"type": "table", "title": results[rid].title, "result_id": rid,
                              "width": "full", "columns": results[rid].column_names()})
                   for rid in allowed]

    used = {w["result_id"] for w in widgets if w.get("result_id")}
    used |= {k["result_id"] for w in widgets for k in (w.get("kpis") or [])}
    filters = []
    for f in spec.get("filters") or []:
        field = f.get("field")
        if field and any(field in results[rid].column_names() for rid in used) and len(filters) < 3:
            filters.append({"field": field, "label": f.get("label") or field, "default": str(f.get("default") or "")})

    clean = {
        "title": spec.get("title") or "Insight",
        "subtitle": spec.get("subtitle") or "",
        "summary": spec.get("summary") or "",
        "widgets": widgets,
        "filters": filters,
        "assumptions": [a for a in spec.get("assumptions") or [] if a][:8],
        "caveats": [c for c in spec.get("caveats") or [] if c][:8],
        "followups": [q for q in spec.get("followups") or [] if q][:4],
    }
    return clean, warnings


def _clean_click(click: dict, cols: list, warnings: list, label: str) -> dict:
    action = click.get("action") or "none"
    out = {"action": "none", "field": "", "question": "", "pillar": "", "view": "", "payload_key": ""}
    if action == "none":
        return out
    field = click.get("field") or ""
    if field not in cols:
        warnings.append(f"{label}: click field '{field}' not in result")
        return out
    if action == "filter":
        return {**out, "action": "filter", "field": field}
    if action == "ask":
        q = click.get("question") or ""
        if "{value}" not in q:
            q = (q + " {value}").strip() if q else "Tell me more about {value}"
        return {**out, "action": "ask", "field": field, "question": q}
    if action == "navigate":
        key = (click.get("pillar"), click.get("view"))
        page = PAGES.get(key)
        if not page or click.get("payload_key") not in page["payload"]:
            warnings.append(f"{label}: navigate target {key}/{click.get('payload_key')} is not a page")
            return out
        return {**out, "action": "navigate", "field": field, "pillar": key[0], "view": key[1],
                "payload_key": click["payload_key"]}
    return out


def _defaults(w: dict) -> dict:
    base = {"type": "table", "title": "", "subtitle": "", "result_id": "", "width": "full", "x": "",
            "y": [], "series": "", "label": "", "size": "", "aggregate": "none",
            "orientation": "vertical", "stacked": False, "sort": "none", "limit": 0,
            "format": "number", "highlight": "", "filter_field": "", "filter_value": "",
            "columns": [], "kpis": [], "text": "",
            "click": {"action": "none", "field": "", "question": "", "pillar": "", "view": "",
                      "payload_key": ""}}
    out = {**base, **{k: v for k, v in w.items() if v is not None}}
    out["id"] = uuid.uuid4().hex[:8]
    return out


def hydrate(spec: dict, results: dict, question: str) -> dict:
    """Attach the rows of every result set the view uses."""
    used = {w["result_id"] for w in spec["widgets"] if w.get("result_id")}
    used |= {k["result_id"] for w in spec["widgets"] for k in (w.get("kpis") or [])}
    return {**spec, "id": uuid.uuid4().hex[:12], "question": question,
            "created": int(time.time() * 1000),
            "data": {rid: results[rid].public() for rid in sorted(used) if rid in results}}

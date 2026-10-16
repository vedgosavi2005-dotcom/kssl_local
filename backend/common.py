"""Helpers shared by the area builders: read a table out of the loaded database, tidy values."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def text(value: Any) -> str:
    return "" if value is None else str(value)


def first_nonempty(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def rows_by_id(rows: list[dict[str, Any]], *names: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        key = first_nonempty(row, *names)
        if key is not None:
            result[str(key)] = row
    return result


def table(database: dict[str, dict[str, list[dict[str, Any]]]], schema: str, name: str) -> list[dict[str, Any]]:
    return database.get(schema, {}).get(name, [])

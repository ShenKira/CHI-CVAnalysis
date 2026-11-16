"""Persistence helpers for user-defined I-T horizontal references."""
from __future__ import annotations

from copy import deepcopy
from uuid import uuid4


def references_from_options(options):
    """Return detached reference records; retain old single-line projects."""
    records = options.get("it_y_references")
    if isinstance(records, list):
        result = deepcopy([record for record in records if isinstance(record, dict)])
        seen = set()
        for index, record in enumerate(result):
            identifier = record.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in seen:
                identifier = f"reference-{index}"
                while identifier in seen:
                    identifier += "-"
                record["id"] = identifier
            seen.add(identifier)
        return result
    if options.get("it_y_reference_value") is None:
        return []
    return [{"id": "legacy", "value": options.get("it_y_reference_value"),
             "unit": deepcopy(options.get("it_y_reference_unit")),
             "label": options.get("it_y_reference_label") or "",
             "color": "#666666", "legend_mode": "hidden", "legend_label": ""}]


def new_reference_id():
    return uuid4().hex


def store_references(options, records):
    options["it_y_references"] = deepcopy(records)
    for key in ("it_y_reference_value", "it_y_reference_unit", "it_y_reference_label"):
        options.pop(key, None)

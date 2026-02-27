"""Infer JSON schema information from sample records."""

from __future__ import annotations


def _python_type(value: object) -> str:
    """Map a Python value to a simple type string."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def infer_schema(sample_records: list[dict]) -> dict:
    """Return a schema description from sample records.

    Returns a dict with:
      - fields: list of {name, type, required}
      - id_field: detected id field name or None
      - partition_key: partition key path (default /id)
    """
    field_types: dict[str, set[str]] = {}
    field_counts: dict[str, int] = {}
    total = len(sample_records)

    for record in sample_records:
        for key, value in record.items():
            field_types.setdefault(key, set()).add(_python_type(value))
            field_counts[key] = field_counts.get(key, 0) + 1

    fields = []
    for name, types in field_types.items():
        dominant_type = max(types, key=lambda t: sum(1 for r in sample_records if _python_type(r.get(name)) == t))
        fields.append(
            {
                "name": name,
                "type": dominant_type,
                "required": field_counts[name] == total,
            }
        )

    id_field = None
    for candidate in ("id", "ID", "_id"):
        if candidate in field_types:
            id_field = candidate
            break

    return {
        "fields": fields,
        "id_field": id_field,
        "partition_key": "/id",
    }


def schema_summary(schema: dict) -> str:
    """Human-readable schema summary for prompt construction."""
    lines = []
    for f in schema["fields"]:
        req = "required" if f["required"] else "optional"
        lines.append(f"  - {f['name']}: {f['type']} ({req})")
    id_note = f"ID field: {schema['id_field']}" if schema["id_field"] else "No id field detected — UUIDs will be generated"
    return f"Fields:\n" + "\n".join(lines) + f"\n{id_note}\nPartition key: {schema['partition_key']}"

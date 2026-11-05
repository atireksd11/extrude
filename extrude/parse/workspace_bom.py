"""CSV facts with explicit reference, part, quantity, and population semantics."""

import csv
from io import StringIO
import re

MAX_BOM_BYTES = 1024 * 1024
MAX_ROWS = 2000
MAX_REFERENCES = 10000
MAX_COLUMNS = 64
_REF = re.compile(r"[A-Za-z]+\d+")


def references(value: str) -> tuple[str, ...] | None:
    result = []
    for token in re.split(r"[,;\s]+", value.strip()):
        if not token:
            continue
        if _REF.fullmatch(token):
            result.append(token.upper())
        else:
            span = re.fullmatch(r"([A-Za-z]+)(\d+)-([A-Za-z]+)(\d+)", token)
            if not span or span[1].upper() != span[3].upper():
                return None
            start, end = int(span[2]), int(span[4])
            if end < start or end - start > 200:
                return None
            result.extend(f"{span[1].upper()}{n}" for n in range(start, end + 1))
    return tuple(result) if result and len(result) == len(set(result)) else None


def _csv_facts(data: bytes, delimiter=",") -> dict:
    if len(data) > MAX_BOM_BYTES:
        raise ValueError("BOM exceeds the 1 MiB analysis limit.")
    stream = StringIO(data.decode("utf-8-sig"), newline="")
    reader = csv.DictReader(stream, delimiter=delimiter, strict=True)
    columns = reader.fieldnames
    if not columns or len(columns) > MAX_COLUMNS or len(columns) != len(set(columns)) or any(not name or len(name) > 100 for name in columns):
        raise ValueError("BOM headers are missing, duplicated, or invalid.")
    rows = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"BOM row near line {reader.line_num} has an inconsistent column count.")
        rows.append(dict(line=reader.line_num, fields=row))
        if len(rows) > MAX_ROWS:
            raise ValueError("BOM exceeds the 2,000-row analysis limit.")
    return dict(columns=columns, rows=rows, total_rows=len(rows))


def csv_facts(data: bytes, delimiter=",") -> dict:
    try:
        return _csv_facts(data, delimiter)
    except csv.Error as exc:
        raise ValueError("CSV quoting or structure is unreadable; BOM checks are unverified.") from exc


def compare_csv(before: dict | None, after: dict | None) -> dict:
    """Exact keyed cells, not inferred schematic references or fuzzy matches."""
    columns = list(dict.fromkeys([*(after or {}).get("columns", []), *(before or {}).get("columns", [])]))
    common = set((before or after or {}).get("columns", [])) & set((after or before or {}).get("columns", []))
    key_column = None
    for alias in ("item", "reference", "references", "ref", "part number", "mpn", "part"):
        found = [col for col in columns if col in common and col.strip().casefold() == alias]
        if len(found) == 1:
            key_column = found[0]
            break
    def index(facts):
        result = {}
        for row in (facts or {}).get("rows", []):
            key = row["fields"].get(key_column, "").strip()
            result.setdefault(key, []).append(row)
        return result
    old, new = index(before), index(after)
    rows, changed_cells = [], 0
    for key in dict.fromkeys([*new, *old]):
        a, b = old.get(key, []), new.get(key, [])
        if not key_column or not key or len(a) > 1 or len(b) > 1:
            # Ambiguity on either side invalidates the match on both sides.
            rows.extend(dict(key=key, status="unverified", before=row, after=None, changes=[]) for row in a)
            rows.extend(dict(key=key, status="unverified", before=None, after=row, changes=[]) for row in b)
            continue
        left, right = a[0] if a else None, b[0] if b else None
        changes = [dict(column=col, before=left["fields"].get(col), after=right["fields"].get(col))
                   for col in columns if left and right and left["fields"].get(col) != right["fields"].get(col)]
        status = "added" if not left else "removed" if not right else "modified" if changes else "unchanged"
        changed_cells += len(changes)
        rows.append(dict(key=key, status=status, before=left, after=right, changes=changes))
    return dict(columns=columns, key_column=key_column, rows=rows, changed_cells=changed_cells,
                added=sum(row["status"] == "added" for row in rows), removed=sum(row["status"] == "removed" for row in rows),
                modified=sum(row["status"] == "modified" for row in rows),
                ambiguous=sum(row["status"] == "unverified" for row in rows),
                added_columns=[col for col in (after or {}).get("columns", []) if before and col not in before["columns"]],
                removed_columns=[col for col in (before or {}).get("columns", []) if after and col not in after["columns"]],
                detail="Rows matched by exact unique " + key_column + "." if key_column else "No shared item/reference/part identifier column; rows are shown without guessing matches.")


def read_bom(data: bytes, mapping) -> dict:
    raw = csv_facts(data, mapping.delimiter)
    required = {mapping.reference_column, mapping.part_column, mapping.quantity_column}
    if mapping.dnp_column:
        required.add(mapping.dnp_column)
    if not required.issubset(raw["columns"]):
        raise ValueError("Configured BOM columns were not found: " + ", ".join(sorted(required - set(raw["columns"]))))
    result, issues, seen, ambiguous = [], [], set(), set()
    for row in raw["rows"]:
        fields = row["fields"]
        refs = references(fields[mapping.reference_column])
        qty = fields[mapping.quantity_column].strip()
        quantity = int(qty) if re.fullmatch(r"\d{1,6}", qty) else None
        token = fields[mapping.dnp_column].strip().lower() if mapping.dnp_column else ""
        dnp = token in {"1", "yes", "true", "dnp", "dni", "not fitted", "exclude", "excluded"}
        unknown_dnp = token not in {"", "0", "no", "false", "fitted", "populate"} and not dnp
        part = fields[mapping.part_column].strip()  # Always a string, including leading zeroes.
        if part.upper() in {"DNP", "DNI", "DO NOT POPULATE"}:
            dnp = True
        duplicate = any(ref in seen for ref in refs or ())
        if duplicate:
            ambiguous.update(refs)
        if refs is None or quantity is None or unknown_dnp or duplicate:
            issues.append(dict(line=row["line"], detail="Ambiguous references, quantity, population flag, or duplicate reference; row excluded from missing-part checks."))
            continue
        seen.update(refs)
        if len(seen) > MAX_REFERENCES:
            raise ValueError("BOM exceeds the 10,000-reference analysis limit.")
        result.append(dict(references=refs, part=part, quantity=quantity, dnp=dnp, line=row["line"]))
    return dict(columns=raw["columns"], rows=[r for r in result if not ambiguous.intersection(r["references"])], issues=issues)

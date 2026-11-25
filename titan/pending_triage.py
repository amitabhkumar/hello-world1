"""Order pending evidence for reading. Input and output are JSON (stdin/stdout)."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import sys

MATERIAL = {"results", "guidance", "order", "orders", "award", "awards", "orders/awards",
            "regulatory action", "regulatory actions", "transaction", "transactions"}
REQUIRED = ("event_id", "unanswered_question", "why_it_matters", "next_checkpoint")


def instant(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.utcoffset() is None:
        raise ValueError("Public time and cutoff require a UTC offset")
    return t.astimezone(timezone.utc)


def triage(pending_research, event_metadata, cutoff):
    cutoff = instant(cutoff)
    ranked = []
    seen = set()
    for item in pending_research:
        event_id = item["event_id"]
        if event_id in seen:
            raise ValueError(f"Duplicate event_id: {event_id}")
        seen.add(event_id)
        row = {**event_metadata.get(event_id, {}), **item}
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in REQUIRED):
            raise ValueError(f"Incomplete pending record: {event_id}")
        material = str(row.get("event_type", "")).lower().strip().replace("_", " ") in MATERIAL
        raw = row.get("size_vs_annual_sales")
        ratio = Decimal(str(raw)) if raw is not None else None
        if ratio is not None and (not ratio.is_finite() or ratio < 0):
            raise ValueError(f"Invalid size_vs_annual_sales: {event_id}")
        public = instant(row["public_time"]) if row.get("public_time") else None
        after = public is not None and public > cutoff
        key = (not material, ratio is None, -(ratio or 0), public is None, public,
               row.get("body_read") is not False, event_id)
        ranked.append((after, key, row))
    ranked.sort(key=lambda entry: entry[:2])
    deep, carry = [], []
    for after, _, row in ranked:
        (carry if after or len(deep) >= 12 else deep).append(row)
    return dict(deep_assess=deep, carry_pending=carry, pending_total=len(ranked),
                deep_assess_count=len(deep), carry_pending_count=len(carry))


if __name__ == "__main__":
    json.dump(triage(**json.load(sys.stdin)), sys.stdout, indent=2)
    print()

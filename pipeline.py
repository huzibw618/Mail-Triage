"""
pipeline.py — batch-runs the triage agent over the full inbox.

Reads data/inbox.json, triages every email (with per-email caching so re-runs
are cheap and idempotent), writes cache/results.json (the UI reads this), and
emits cache/run_log.jsonl (structured observability: per-email tokens, latency,
tools, decision). Prints a summary table at the end.
"""

import json
import time
from pathlib import Path
from triage import triage_email
import sys

INBOX = Path("data/inbox.json")
RESULTS = Path("cache/results.json")
RUN_LOG = Path("cache/run_log.jsonl")

CATEGORY_ORDER = ["emergency", "follow_up", "quote", "community",
                  "invoice", "out_of_scope", "spam"]


def _load_cache() -> dict:
    """Existing results keyed by email id, so re-runs skip already-done emails."""
    if RESULTS.exists():
        try:
            return {r["id"]: r for r in json.loads(RESULTS.read_text())}
        except Exception:
            return {}
    return {}


def main(force: bool = False):
    Path("cache").mkdir(exist_ok=True)
    emails = json.loads(INBOX.read_text())["emails"]
    cache = {} if force else _load_cache()

    results = []
    log_lines = []
    t0 = time.time()
    tokens_in = tokens_out = 0
    processed = skipped = 0

    for i, email in enumerate(emails, 1):
        eid = email["id"]
        if eid in cache and not force:
            results.append(cache[eid])
            skipped += 1
            continue

        e_start = time.time()
        r = triage_email(email)
        latency_ms = int((time.time() - e_start) * 1000)

        # flatten the nested `from` into the flat shape the UI expects,
        # and carry through the pass-through fields
        record = {
            "id": eid,
            "sender_name": email["from"]["name"],
            "sender_email": email["from"]["email"],
            "subject": email["subject"],
            "body": email["body"],
            "received_at": email["received_at"],
            "category": r["category"],
            "priority": r["priority"],
            "urgency_reason": r["urgency_reason"],
            "needs_review": r["needs_review"],
            "customer_context": r.get("customer_context"),
            "tools_used": r.get("tools_used", []),
            "draft_reply": r.get("draft_reply"),
        }
        results.append(record)

        usage = r.get("_usage", {"tokens_in": 0, "tokens_out": 0})
        tokens_in += usage["tokens_in"]
        tokens_out += usage["tokens_out"]
        processed += 1

        # structured observability log (one JSON object per line)
        log_lines.append(json.dumps({
            "id": eid,
            "category": r["category"],
            "priority": r["priority"],
            "needs_review": r["needs_review"],
            "tools_used": r.get("tools_used", []),
            "tokens_in": usage["tokens_in"],
            "tokens_out": usage["tokens_out"],
            "latency_ms": latency_ms,
        }))
        print(f"  [{i:>3}/{len(emails)}] {eid}  {r['category']:13} p{r['priority']}  ({latency_ms}ms)")

    # sort by priority for the UI (stable; ties keep arrival order)
    results.sort(key=lambda x: x["priority"])

    RESULTS.write_text(json.dumps(results, indent=2))
    RUN_LOG.write_text("\n".join(log_lines))

    # ---- summary ----
    elapsed = time.time() - t0
    counts = {c: 0 for c in CATEGORY_ORDER}
    for r in results:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    needs_review = sum(1 for r in results if r["needs_review"])

    # Haiku 4.5 pricing (approx, per the docs): adjust if your model differs
    COST_IN = 1.00 / 1_000_000    # $ per input token
    COST_OUT = 5.00 / 1_000_000   # $ per output token
    est_cost = tokens_in * COST_IN + tokens_out * COST_OUT

    print("\n" + "=" * 48)
    print(f"  TRIAGED {len(results)} emails  ({processed} new, {skipped} cached)")
    print(f"  time: {elapsed:.1f}s   tokens: {tokens_in:,} in / {tokens_out:,} out")
    print(f"  est. cost this run: ${est_cost:.4f}  (~${est_cost/max(processed,1):.5f}/email)")
    print("-" * 48)
    for c in CATEGORY_ORDER:
        print(f"  {c:14} {counts[c]:>3}")
    print("-" * 48)
    print(f"  drafts to approve: {needs_review}   auto-filtered (spam): {counts['spam']}")
    print("=" * 48)


if __name__ == "__main__":
    main(force="--force" in sys.argv)
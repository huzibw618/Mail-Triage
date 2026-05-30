"""
triage.py — Possum Patrol inbox triage agent (core logic).

Three retrieval tools read Possum Patrol's records, then a single LLM call
classifies + prioritizes + drafts a reply, grounded in that context.

Design: deterministic pipeline. For each email we always enrich with customer
context (CSV + Marshall's notes + pricing), then make ONE LLM call. We do not
use an autonomous tool-calling loop — the tool order is fixed and known, which
keeps it fast, cheap, and fully explainable.
"""

import os
import json
import csv
import re
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
MODEL = "claude-haiku-4-5-20251001"

_client = None
def get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ----------------------------------------------------------------------------
# TOOLS — retrieval over Possum Patrol's records. These return context strings
# that get injected into the prompt. They do NOT make decisions; the LLM does.
# ----------------------------------------------------------------------------

_customers_cache = None
def _load_customers():
    global _customers_cache
    if _customers_cache is None:
        with open(DATA_DIR / "customers.csv", newline="", encoding="utf-8") as f:
            _customers_cache = list(csv.DictReader(f))
    return _customers_cache


def lookup_customer(email_address: str, sender_name: str = "") -> dict | None:
    """Find a customer by email (preferred) or fuzzy name match.
    Returns the record dict, or None if not a known customer."""
    rows = _load_customers()
    email_address = (email_address or "").strip().lower()
    for row in rows:
        if row.get("email", "").strip().lower() == email_address and email_address:
            return row
    # fall back to name match (some VIPs like Dottie have no email on file)
    name = (sender_name or "").strip().lower()
    if name:
        for row in rows:
            if name in row.get("name", "").strip().lower():
                return row
    return None


def check_vip(email_address: str, sender_name: str) -> str | None:
    """Search Marshall's notes for any block of text mentioning this sender.
    Returns the relevant note text (VIP rules, blocklist, scope quirks), or None.
    This is fuzzy on purpose — Marshall's notes are prose, not a database."""
    notes = (DATA_DIR / "notes_from_marshall.txt").read_text(encoding="utf-8")
    # split notes into blocks separated by blank lines / headers
    blocks = re.split(r"\n\s*\n", notes)
    name = (sender_name or "").strip().lower()
    # use last name + first name tokens as search keys
    tokens = [t for t in re.split(r"[^a-z]+", name) if len(t) > 2]
    hits = []
    for block in blocks:
        bl = block.lower()
        if any(tok in bl for tok in tokens):
            hits.append(block.strip())
    return "\n\n".join(hits) if hits else None


def get_pricing(service_query: str = "") -> str:
    """Return the full services & pricing sheet (it's small). The LLM picks the
    relevant line. Passing the whole sheet is cheaper in dev time than building
    a matcher, and the sheet is short enough that tokens aren't a concern."""
    return (DATA_DIR / "services.md").read_text(encoding="utf-8")


# ----------------------------------------------------------------------------
# THE AGENT — one LLM call does classify + prioritize + draft, given context.
# ----------------------------------------------------------------------------

CATEGORIES = ["emergency", "follow_up", "quote", "community",
              "invoice", "out_of_scope", "spam"]

SYSTEM_PROMPT = """You are the inbox triage agent for Possum Patrol Pest Control, a beloved \
22-year-old family wildlife-removal business in Chattanooga, TN. The owner is Skye Ryder; her \
father Marshall founded it and is now retired. You triage one email at a time so Skye can clear \
~100 emails a morning without missing anything that matters.

You will receive the email plus CONTEXT retrieved from Possum Patrol's records (customer history, \
Marshall's handwritten notes, and the pricing sheet). USE that context — it tells you who is a VIP, \
who is on the do-not-serve blocklist, what discounts apply, and what's out of scope.

Classify each email into exactly ONE category and assign a priority 1 (most urgent) to 5 (least):

- emergency (priority 1): An animal actively in living space, a safety risk, or a commercial \
  health-code/operational crisis. A snake in a baby's crib or a fire-risk outranks a routine \
  raccoon. Commercial emergencies (restaurant before inspection, production line shutdown) are \
  high-value AND urgent.
- follow_up (priority 1-2): An existing relationship at risk — unanswered prior emails, a 3rd/4th \
  follow-up, a complaint, a warranty re-treatment request, a dropped ball. These are how the \
  business LOSES accounts, so they rank high. Threatening to leave = priority 1.
- quote (priority 2): A genuine request for a new job or pricing. VIP or large commercial quotes \
  rank toward priority 1-2.
- community (priority 3): A warm personal note, thank-you, or well-wish. The heart of a 22-year \
  family business — never treat them as noise. They don't need a same-day fix but they DO need a \
  genuine reply. When an email blends a service request with personal or relationship content \
  (grief, long history, asking after Marshall), the draft MUST acknowledge the person warmly \
  BEFORE handling any logistics — lead with the human, then the job.
- invoice (priority 4): A vendor bill, membership due, license/insurance renewal, or financial \
  admin. Bump priority UP if a due date is imminent.
- out_of_scope (priority 4): A real human, but not a job Possum Patrol does. Examples: someone who \
  thinks Possum Patrol is a band (it's not — politely decline), a blocklisted customer (decline \
  per Marshall's script — never offer a warm quote or pricing), or a delusional/non-actionable \
  request (e.g. "raccoons stole my crypto wallet"). These need a human's eyes, NOT auto-trash.
- spam (priority 5): Unsolicited marketing, cold sales, lead-gen, SaaS pitches. No reply.

CRITICAL JUDGMENT RULES:
- If CONTEXT shows the sender is BLOCKLISTED, category is out_of_scope. Draft only the polite \
  brush-off Marshall scripted (e.g. "we're booked out"). Never offer service or pricing.
- If CONTEXT shows a VIP with a discount or special rule (senior discount, church 10%, vet 15%, \
  Dottie's no-bee-jobs, don't-reply-all), the draft MUST honor it.

QUOTING:
- When the email is a genuine quote request and the PRICING SHEET is in context, include the \
  TYPICAL RANGE for the relevant service, framed as an estimate ("usually runs $X-$Y"), and say a \
  firm quote will follow after a quick look. NEVER state a single firm price.
- If CONTEXT shows a VIP discount, apply it and mention it warmly ("with your church discount, \
  closer to $X-$Y").
- Honor Marshall's rules: do NOT quote snake removal sight-unseen (offer to come look instead). \
  Customer-specific rules in the notes apply ONLY to that customer — e.g. the "no bee/wasp jobs" \
  rule is for Dottie ONLY (she's allergic; gently decline if SHE asks). For every other sender, \
  bee, wasp, yellow-jacket, and hornet removal is a NORMAL job — quote it or, if it's a safety \
  emergency (swarm blocking entry, someone stung), treat it as an emergency. Never generalize one \
  customer's special rule to others.
- For large, commercial, or complex jobs (multi-building RFQs, whole-home plans, contracts), do \
  NOT force a residential range — say you'll prepare a written proposal.

VOICE for drafts: warm, folksy, personal, like a family business that's known these people for \
years. Sign as "Skye, Possum Patrol." Reference shared history when the context provides it. \
Keep drafts short (2-4 sentences). For spam, draft_reply must be null.

REVIEW: The agent NEVER auto-sends. Set needs_review = true whenever draft_reply is non-null \
(a human approves every outgoing reply). Set needs_review = false ONLY when draft_reply is null \
(spam — no reply needed).

Respond with ONLY a JSON object, no other text, no markdown fences:
{
  "category": one of the categories above,
  "priority": integer 1-5,
  "urgency_reason": one sentence explaining the priority,
  "needs_review": boolean,
  "draft_reply": string or null,
  "customer_context": one short sentence summarizing what the records told you, or null
}"""


def _build_context(email: dict) -> tuple[str, list[str]]:
    """Run the retrieval tools and assemble a context block. Returns
    (context_string, list_of_tools_that_returned_something)."""
    sender_email = email["from"]["email"]
    sender_name = email["from"]["name"]
    parts = []
    tools_used = []

    cust = lookup_customer(sender_email, sender_name)
    if cust:
        tools_used.append("lookup_customer")
        parts.append(
            f"CUSTOMER RECORD: {cust['name']} | jobs: {cust['total_jobs']} | "
            f"revenue: ${cust['total_revenue_usd']} | last service: {cust['last_service_date']} | "
            f"notes: {cust.get('notes') or '(none)'}"
        )

    vip = check_vip(sender_email, sender_name)
    if vip:
        tools_used.append("check_vip")
        parts.append(f"MARSHALL'S NOTES (relevant):\n{vip}")

    # only attach pricing sheet when the email plausibly wants a quote (saves tokens)
    body_l = (email.get("subject", "") + " " + email.get("body", "")).lower()
    if any(k in body_l for k in ["quote", "estimate", "price", "how much", "rate", "cost", "$"]):
        tools_used.append("get_pricing")
        parts.append(f"PRICING SHEET:\n{get_pricing()}")

    context = "\n\n".join(parts) if parts else "(No matching records. Treat as a new/unknown sender.)"
    return context, tools_used


def triage_email(email: dict) -> dict:
    """Classify, prioritize, and draft a reply for one email. Returns the
    enriched result dict (UI-ready shape, minus pass-through fields)."""
    context, tools_used = _build_context(email)

    user_msg = (
        f"CONTEXT:\n{context}\n\n"
        f"--- EMAIL ---\n"
        f"From: {email['from']['name']} <{email['from']['email']}>\n"
        f"Subject: {email['subject']}\n"
        f"Body: {email['body']}"
    )

    try:
        resp = get_client().messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        usage = {"tokens_in": resp.usage.input_tokens,
                 "tokens_out": resp.usage.output_tokens}
    except Exception as e:
        # Fail safe: never silently drop an email. Give it a placeholder draft
        # so it surfaces in the approval queue (a failed email might be urgent).
        result = {
            "category": "follow_up", "priority": 2,
            "urgency_reason": f"Automatic triage failed ({type(e).__name__}); needs manual review.",
            "draft_reply": "[Triage failed for this email — please review and reply manually.]",
            "customer_context": None,
        }
        usage = {"tokens_in": 0, "tokens_out": 0}

    # guard rails on the model output
    if result.get("category") not in CATEGORIES:
        result["category"] = "follow_up"
    result["priority"] = int(result.get("priority", 3))
    # enforce the invariant: review is true iff there's a draft to approve
    result["needs_review"] = result.get("draft_reply") is not None
    result["tools_used"] = tools_used
    result["_usage"] = usage
    return result
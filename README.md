# Possum Patrol — AI Inbox Triage

An AI agent that triages a small family business's inbox: classifies emails, prioritizes them, and drafts warm replies grounded in the business's real customer records. Turns a 3-hour morning inbox crawl into a 4-minute approval queue.

---

## The Problem

Skye Ryder runs Possum Patrol, a 22-year-old wildlife-removal business in Chattanooga that gets ~100 mixed emails every morning — live animal emergencies, commercial quote requests, vendor invoices, warm community notes, and spam all arrive in the same inbox. Triaging by hand costs her roughly 3 hours a day, and the cost isn't just time: missed follow-ups have lost accounts.

---

## What It Does

- Classifies each email into one of **7 categories** with a priority (1 = most urgent):

  | Category | Priority | Meaning |
  |---|---|---|
  | `emergency` | 1 | Animal in living space, safety risk, commercial health-code crisis |
  | `follow_up` | 1–2 | At-risk relationship — unanswered emails, complaints, warranty re-treatments |
  | `quote` | 2 | New job or pricing request |
  | `community` | 3 | Warm notes, thank-yous — the heart of a family business |
  | `invoice` | 4 | Vendor bills, renewals, financial admin |
  | `out_of_scope` | 4 | Real humans but not Possum Patrol's work (wrong number, blocklisted customers) |
  | `spam` | 5 | Cold sales, lead-gen — no reply drafted |

- Drafts a reply in the family business's voice, grounded in real customer history.
- **Never auto-sends.** Every drafted reply sits in a priority-sorted approval queue; Skye clicks Approve and sends manually.
- Surfaces its reasoning: why this priority, which records it checked, what the draft is based on.

---

## Architecture

```
data/inbox.json
data/customers.csv          pipeline.py          cache/results.json
data/services.md        ──────────────────>      cache/run_log.jsonl      ──>  app.py
data/notes_from_marshall.txt   (batch, cached)   (proof-of-work artifact)      (Streamlit viewer)
```

**Three files, one job each:**

- **`triage.py`** — the agent core. For every email: runs three retrieval tools to build context, then makes a single LLM call (`claude-haiku-4-5`) that classifies, prioritizes, explains, and drafts — all in one structured JSON response. Tools are deterministic and ordered; no autonomous loop.
  - `lookup_customer` — email/name lookup against `customers.csv`
  - `check_vip` — fuzzy search over Marshall's handwritten prose notes
  - `get_pricing` — attaches the pricing sheet only when the email plausibly wants a quote (saves tokens)

- **`pipeline.py`** — batch runner. Loads `inbox.json`, skips already-processed IDs (idempotent re-runs), calls `triage_email()` for each new email, writes `cache/results.json` (what the UI reads) and `cache/run_log.jsonl` (per-email tokens, latency, tools used). Prints a cost/category summary on exit.

- **`app.py`** — pure Streamlit viewer. Reads `cache/results.json` only — no API calls, no imports from `triage.py`. Provides a Gmail-style label rail (7 categories + counts), priority-sorted approval queue, and per-card draft editing with an Approve button. Cache invalidates on file `mtime` so a fresh pipeline run appears on the next browser refresh.

**Why compute and display are decoupled:**
The UI runs without an API key (the results file is the artifact). It gives a clean demo boundary, caps cost to a single pipeline run, and mirrors a production pattern where batch inference and serving are separate concerns.

---

## Setup & Run

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv)

```bash
# 1. Install dependencies
uv sync

# 2. Set your API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# 3. Place data files in data/
#    inbox.json, customers.csv, services.md, notes_from_marshall.txt
source  .venv/bin/activate
# 4. Run the triage pipeline
python pipeline.py          # re-run with --force to re-process cached emails

# 5. Open the approval queue
streamlit run app.py
```

> **Note:** `cache/results.json` is committed as a proof-of-work artifact — the Streamlit UI runs without an API key.

---

## Design Decisions & Tradeoffs

- **Deterministic pipeline over an autonomous tool-calling loop.** The three retrieval tools always run in the same order. This is faster, cheaper (one LLM call per email vs. many), and fully explainable — the run log shows exactly what context each decision was based on.

- **Human-in-the-loop on every draft.** The failure modes are asymmetric: a missed emergency or a badly-worded reply to a 20-year customer costs far more than the 5 seconds it takes Skye to click Approve.

- **Lexical retrieval over vector RAG.** The corpus is small and structured. Email-match + name-token search is fast, zero-infrastructure, and produces no false matches from semantic similarity. Worth revisiting if Marshall's notes grow beyond a few pages.

- **Streamlit over a production frontend.** The right tool for a working demo that a non-technical grader can run in one command.

---

## What I'd Do With Another Day

- **Live Gmail integration** — pull directly from the Gmail API and write approved drafts back as Gmail drafts.
- **Identity resolution** — handle "Janet Cole" vs. "janet.cole@gmail.com" vs. "Mrs. Cole" as the same person across the customer record, notes, and inbox.
- **Vector retrieval** for Marshall's notes if the corpus grows (right now it's prose that fits in one prompt injection).
- **Per-category accuracy eval** — a small labeled test set to catch regressions when the prompt or model changes.
- **Learning loop** — treat Skye's edits to the draft text_area as a signal; log diffs to improve the system prompt over time.

---

## Stack

Python 3.12 · Anthropic API (`claude-haiku-4-5-20251001`) · Streamlit · pandas · no framework

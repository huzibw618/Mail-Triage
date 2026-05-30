# Possum Patrol — Mail Triage

AI-assisted email triage for a small wildlife-removal business: classifies incoming emails (emergency / quote / community / invoice / spam), drafts warm replies in the Possum Patrol voice, and flags items that need a human to approve.

## Setup

```bash
uv add anthropic python-dotenv streamlit pandas
# add ANTHROPIC_API_KEY to .env
```

## Run

```bash
# 1. Process inbox → writes enriched results to cache/results.json
python pipeline.py

# 2. Review and approve drafts in the browser
streamlit run app.py
```

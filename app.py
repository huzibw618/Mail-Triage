"""
Streamlit viewer for triaged Possum Patrol emails — Gmail-calm / Notion-tag restyled.

Reads cache/results.json — no LLM calls, display only.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

CACHE_PATH = Path("cache/results.json")

# Notion-on-dark palette: (tag_bg, tag_text, left_border_accent)
_PALETTE: dict[str, tuple[str, str, str]] = {
    "emergency":    ("#4A2228", "#F4A0A8", "#C0606A"),
    "follow_up":    ("#4A3A1A", "#F0C277", "#C4902A"),
    "quote":        ("#1E3247", "#8FC1EC", "#5A9FD4"),
    "community":    ("#1B3A28", "#84DBA6", "#4AC47A"),
    "invoice":      ("#2A2E36", "#C2C8D2", "#8A8F99"),
    "out_of_scope": ("#3A2A40", "#C79FDB", "#9B6ABF"),
    "spam":         ("#24262B", "#969BA5", "#555963"),
}

# Category-specific emoji prefix used in collapsed expander labels
_PREFIX: dict[str, str] = {
    "emergency":    "🚨",
    "follow_up":    "🔔",
    "quote":        "💰",
    "community":    "❤️",
    "invoice":      "🧾",
    "out_of_scope": "⚠️",
    "spam":         "🗑️",
}

# Sort rank for categories — lower = shown first
_CAT_RANK: dict[str, int] = {
    "emergency":    0,
    "follow_up":    1,
    "quote":        2,
    "community":    3,
    "invoice":      4,
    "out_of_scope": 5,
    "spam":         6,
}


def _parse_ts(received_at: str | None) -> float:
    """Parse an ISO-8601 timestamp into a float for sorting. Returns 0.0 on failure."""
    if not received_at:
        return 0.0
    try:
        from datetime import datetime, timezone
        s = received_at.rstrip("Z").split("+")[0]  # strip tz, keep up to seconds
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


# Human-readable names for tool calls surfaced in the card
_TOOL_LABELS: dict[str, str] = {
    "lookup_customer": "customer records",
    "check_vip":       "Marshall's notes",
    "get_pricing":     "pricing guide",
}

_PILL_BASE = (
    "display:inline-block;"
    "padding:2px 10px;"
    "border-radius:6px;"
    "font-size:11px;"
    "font-weight:600;"
    "letter-spacing:0.4px;"
    "text-transform:uppercase;"
)


def _pill(category: str, label: str | None = None) -> str:
    bg, fg, _ = _PALETTE.get(category, _PALETTE["spam"])
    text = label if label is not None else category
    return f'<span style="{_PILL_BASE}background:{bg};color:{fg};">{text}</span>'


def _accent(category: str) -> str:
    return _PALETTE.get(category, _PALETTE["spam"])[2]


@st.cache_data
def load_results(_mtime: float) -> list[dict]:
    # _mtime is the file's modification time — changing it busts the cache key
    # so a new pipeline run is picked up automatically on the next browser refresh.
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return []


def _inject_css() -> None:
    st.markdown("""
<style>
/* ── Layout ─────────────────────────────────────────── */
.block-container { padding-top: 2.5rem !important; max-width: 1150px; }

/* ── Heading ─────────────────────────────────────────── */
h1 {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.3px;
    margin-bottom: 0 !important;
}

/* ── Expander card ───────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #252830 !important;
    border-radius: 8px !important;
    margin-bottom: 4px !important;
    background: #13161E !important;
    transition: border-color 0.15s;
}
[data-testid="stExpander"]:hover {
    border-color: #363A46 !important;
}

/* Expander toggle row */
[data-testid="stExpander"] summary {
    font-size: 1rem !important;
    padding: 10px 16px !important;
    border-radius: 7px !important;
    color: #C8CDD6 !important;
}
[data-testid="stExpander"] summary:hover {
    background: #1A1D27 !important;
}

/* ── Sidebar shell ───────────────────────────────────── */
[data-testid="stSidebar"] { background: #0C0F15 !important; }
[data-testid="stSidebar"] h3 { font-size: 0.85rem !important; color: #888 !important; }

/* ── Gmail-style nav rail (st.radio) ────────────────── */
/* Hide the actual radio dot + input */
[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    display: none !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label > span:first-child {
    display: none !important;
}
/* Each option row */
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    display: flex !important;
    align-items: center !important;
    padding: 7px 12px !important;
    border-radius: 6px !important;
    margin: 1px 4px !important;
    cursor: pointer !important;
    font-size: 1rem !important;
    color: #8A8F9A !important;
    transition: background 0.12s, color 0.12s !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #1A1E2A !important;
    color: #C8CDD6 !important;
}
/* Selected row — :has() is supported in all modern browsers */
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: #1C2840 !important;
    color: #8FC1EC !important;
    font-weight: 600 !important;
}
/* Collapse default gap between options */
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    gap: 0 !important;
}

/* ── Metrics ─────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #13161E;
    border: 1px solid #252830;
    border-radius: 8px;
    padding: 10px 16px !important;
}
[data-testid="stMetricValue"] { font-size: 1.65rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.75rem !important; color: #777 !important; }

/* ── Draft textarea ──────────────────────────────────── */
textarea {
    font-size: 0.86em !important;
    line-height: 1.6 !important;
    background: #0E1117 !important;
}

/* ── Divider ─────────────────────────────────────────── */
hr { border-color: #252830 !important; margin: 8px 0 !important; }
</style>
""", unsafe_allow_html=True)


def _card_header(email: dict, category: str) -> None:
    """Render the styled card header inside an expanded row."""
    is_emergency = category == "emergency"
    needs_review = email.get("needs_review", False)
    accent = _accent(category)
    emergency_bg = "background:#160A0C;" if is_emergency else "background:#10131A;"

    emoji = _PREFIX.get(category, "")
    pill_label = f"{emoji} {category}".strip() if emoji else category
    badges = _pill(category, pill_label)
    if needs_review:
        badges += ' <span style="color:#F0B429;font-size:0.82em;">⚠ needs review</span>'

    body_teaser = email.get("body", "")
    teaser = (body_teaser[:70] + "…") if len(body_teaser) > 70 else body_teaser

    st.markdown(f"""
<div style="border-left:3px solid {accent};padding:10px 16px;border-radius:0 6px 6px 0;{emergency_bg}margin-bottom:12px;">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">{badges}</div>
  <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:4px;">
    <span style="font-weight:700;color:#E8ECF2;font-size:1em;">{email.get('sender_name','—')}</span>
    <span style="color:#6B7280;font-size:0.875em;">&lt;{email.get('sender_email','')}&gt;</span>
  </div>
  <div style="display:flex;align-items:baseline;gap:6px;font-size:0.92em;flex-wrap:wrap;">
    <span style="color:#C8CDD6;font-weight:500;">{email.get('subject','')}</span>
    <span style="color:#3D4048;">—</span>
    <span style="color:#6B7280;">{teaser}</span>
  </div>
</div>
""", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Possum Patrol — Mail Triage",
        page_icon="📬",
        layout="wide",
    )
    _inject_css()

    mtime  = CACHE_PATH.stat().st_mtime if CACHE_PATH.exists() else 0
    emails = load_results(mtime)

    if not emails:
        st.warning("No triaged results found — run `python pipeline.py` first.")
        return

    total          = len(emails)
    drafts_total   = sum(1 for e in emails if e.get("draft_reply"))
    auto_filtered  = total - drafts_total
    approved_count = sum(
        1 for e in emails
        if st.session_state.get(f"approved_{e.get('id','')}", False)
    )
    drafts_pending = max(drafts_total - approved_count, 0)

    # ── Header ───────────────────────────────────────────────────────────────
    st.title("📬 Mail Triage")
    st.caption(
        f"{drafts_total} drafts ready for your approval · "
        f"{auto_filtered} auto-filtered · "
        f"sorted so nothing urgent hides"
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Total", total)
    with m2:
        st.metric("Drafts to approve", drafts_pending)
    with m3:
        st.metric("Approved", approved_count)

    st.divider()

    # ── Sidebar nav ───────────────────────────────────────────────────────────
    _NAV = [
        ("📥", "All",          None),
        ("🚨", "Emergency",    "emergency"),
        ("🔔", "Follow-ups",   "follow_up"),
        ("💰", "Quotes",       "quote"),
        ("❤️", "Community",   "community"),
        ("🧾", "Invoices",     "invoice"),
        ("⚠️", "Out of scope", "out_of_scope"),
        ("🗑️", "Spam",         "spam"),
    ]

    cat_counts: dict = {cat: sum(1 for e in emails if e.get("category") == cat)
                        for _, _, cat in _NAV if cat is not None}
    cat_counts[None] = total

    nav_options = [f"{emoji}  {label}  ({cat_counts.get(cat, 0)})"
                   for emoji, label, cat in _NAV]

    st.sidebar.markdown(
        '<p style="font-size:0.68rem;font-weight:700;letter-spacing:1.2px;'
        'color:#444;text-transform:uppercase;margin:12px 12px 6px;">Possum Patrol</p>',
        unsafe_allow_html=True,
    )
    nav_choice = st.sidebar.radio("nav", nav_options, index=0, label_visibility="collapsed")
    selected_cat = _NAV[nav_options.index(nav_choice)][2]  # None = All

    st.sidebar.divider()
    approval_queue_only = st.sidebar.checkbox("Approval queue only", value=False)

    # ── Filter + sort ─────────────────────────────────────────────────────────
    visible = [
        e for e in emails
        if (selected_cat is None or e["category"] == selected_cat)
        and (not approval_queue_only or e.get("draft_reply"))
    ]
    visible.sort(key=lambda e: (
        e.get("priority", 99),
        _CAT_RANK.get(e.get("category", ""), 99),
        -_parse_ts(e.get("received_at")),   # newest first within a tie
    ))

    if not visible:
        st.info("No emails match the current filters.")
        return

    # ── Email rows ────────────────────────────────────────────────────────────
    for email in visible:
        eid      = email.get("id", "")
        category = email.get("category", "unknown")
        priority = email.get("priority", "?")
        body     = email.get("body", "")
        snippet  = (body[:65] + "…") if len(body) > 65 else body

        is_emergency = category == "emergency"
        needs_review = email.get("needs_review", False)
        draft        = email.get("draft_reply")

        # Resolve approved state before building the label so the ✓ mark is live
        approved_key = f"approved_{eid}"
        if approved_key not in st.session_state:
            st.session_state[approved_key] = False
        is_approved = st.session_state[approved_key]

        # Plain-text label — Streamlit escapes HTML in expander titles.
        prefix       = _PREFIX.get(category, "▎")
        review_flag  = "  ⚠" if needs_review else ""
        approve_mark = "  ✓" if is_approved else ""
        subject      = email.get("subject", "(no subject)")
        sender       = email.get("sender_name", "—")
        label = f"{prefix}  P{priority}   {sender}   ·   {subject[:48]}   —   {snippet[:55]}{review_flag}{approve_mark}"

        with st.expander(label, expanded=is_emergency):
            _card_header(email, category)

            # Approved banner — top of card so the eye lands on it and moves on
            if is_approved:
                st.success("✓ Approved — ready to send")

            # Urgency insight
            urgency = email.get("urgency_reason", "")
            if urgency:
                st.info(f"**Why this matters:** {urgency}")

            # Tools the agent used (grouped with urgency so reasoning is visible)
            tools_used = email.get("tools_used") or []
            if tools_used:
                readable = [_TOOL_LABELS.get(t, t.replace("_", " ")) for t in tools_used]
                st.caption(f"🔧 Checked: {', '.join(readable)}")

            # Customer context
            ctx = email.get("customer_context")
            if ctx:
                st.caption(f"👤  {ctx}")

            # Original message
            st.markdown(
                '<p style="color:#444;font-size:0.76em;margin:14px 0 4px 0;letter-spacing:0.3px;">— original message —</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="color:#8A8F99;font-size:0.86em;line-height:1.65;'
                f'padding:10px 14px;background:#0C0F14;border-radius:5px;'
                f'border:1px solid #1E2128;">{body}</div>',
                unsafe_allow_html=True,
            )

            st.divider()

            # Draft reply + approve action
            if draft:
                st.text_area("Draft reply", value=draft, key=f"draft_{eid}",
                             height=120, disabled=is_approved)
                if not is_approved:
                    if st.button("✅ Approve", key=f"approve_{eid}", type="primary"):
                        st.session_state[approved_key] = True
                        st.rerun()
            else:
                st.markdown(
                    '<p style="color:#555;font-size:0.84em;padding:4px 0;">'
                    'No reply needed — auto-filtered.</p>',
                    unsafe_allow_html=True,
                )


if __name__ == "__main__":
    main()

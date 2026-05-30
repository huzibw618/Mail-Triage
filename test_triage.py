import json
from triage import triage_email, lookup_customer, check_vip

# 1. Tools first — these must work or the whole thing is blind
print("== TOOL CHECK ==")
print("Mike Poteet VIP note:", check_vip("mpoteet1985@yahoo.com", "Mike Poteet")[:80] if check_vip("mpoteet1985@yahoo.com", "Mike Poteet") else "NOT FOUND  <-- BUG")
print("Tony lookup:", (lookup_customer("tony@lookoutgrille.com") or {}).get("total_revenue_usd", "NOT FOUND <-- BUG"))

# 2. Trap emails — load real ones from the inbox
emails = {e["id"]: e for e in json.load(open("data/inbox.json"))["emails"]}
traps = ["msg_0031", "msg_0032", "msg_0033", "msg_0055", "msg_0035", "msg_0013"]
#         Poteet     band       crypto     snake-crib  Eleanor    spam

print("\n== TRAP CHECK ==")
for tid in traps:
    r = triage_email(emails[tid])
    print(f"{tid}: {r['category']:13} p{r['priority']} review={r['needs_review']} "
          f"tools={r['tools_used']}  | {r['urgency_reason'][:60]}")
    

r = triage_email(emails["msg_0035"])
print("\n== ELEANOR'S DRAFT ==")
print(r["draft_reply"])
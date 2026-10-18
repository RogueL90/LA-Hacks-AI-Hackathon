import json
p = json.load(open("logs/asi1_plan.json"))
print("  plan_status:", p.get("plan_status"))
for pid, ph in sorted(p.get("phases", {}).items()):
    for tid, t in ph["tasks"].items():
        c = t.get("agent_card_response") or {}
        d = c.get("card_details") or {}
        sp = (d.get("payload") or {}).get("schema_payload", {})
        print(f"  step {pid}.{tid}: {t['status']} | sent: {(t.get('agent_message') or '')[:160]!r}")
        if t.get("agent_response"):
            print("     text reply:", t["agent_response"][:300].replace("\n", " "))
        if d:
            print("     card:", d.get("card_kind"), sp.get("title") or (sp.get("root") or {}).get("title"), "| narration:", (c.get("chat_message") or "")[:220])
        if t.get("payment_request"):
            print("     payment_request:", json.dumps(t["payment_request"])[:300])

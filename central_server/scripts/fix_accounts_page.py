from pathlib import Path

p = Path(__file__).resolve().parents[1] / "frontend/src/pages/AccountsPage.tsx"
text = p.read_text(encoding="utf-8")
start = text.index("  return (")
head = text[:start]
tail = Path(__file__).with_name("_accounts_tail.tsx").read_text(encoding="utf-8")
p.write_text(head + tail, encoding="utf-8")
print("ok")

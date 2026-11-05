from fastapi.testclient import TestClient
from main import app
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

c = TestClient(app)
tests = [
    "What is the tomato price in Chennai?",
    "Which market has the cheapest onion price?",
    "Compare the prices of potatoes in Tamil Nadu and Kerala.",
    "Which market has the lowest tomato price in Tamil Nadu?",
    "Show me tomato prices in Tamil Nadu.",
    "Hello world test",
]
for q in tests:
    r = c.post("/api/ask", json={"question": q})
    d = r.json()
    print(f"\n>>> {q}")
    print(f"  intent={d['intent']} count={d['count']} | {d['answer'][:110]}")
    print(f"  rows={d['rows'][:2]}")
print("\n/meta:", c.get("/api/meta").json())
print("/health:", c.get("/api/health").json())
print("ALL OK")

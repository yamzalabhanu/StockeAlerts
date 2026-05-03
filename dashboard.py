from fastapi import FastAPI
from storage import load_results

app = FastAPI()

@app.get("/")
def home():
    data = load_results()
    return {
        "total_signals": len(data),
        "recent": data[-10:]
    }

@app.get("/stats")
def stats():
    data = load_results()
    wins = sum(1 for d in data if d.get("outcome") == "WIN")
    losses = sum(1 for d in data if d.get("outcome") == "LOSS")

    total = len(data)
    win_rate = (wins / total * 100) if total > 0 else 0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2)
    }

from fastapi import FastAPI
from storage import load_results, performance_summary

app = FastAPI(title="AI Swing Trader Dashboard")

@app.get("/")
def home():
    data = load_results()
    return {
        "total_signals": len(data),
        "recent": data[-10:]
    }

@app.get("/performance")
def performance():
    return performance_summary()

@app.get("/trades")
def trades():
    return load_results()

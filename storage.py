import json
from pathlib import Path

DATA_FILE = Path("results.json")


def save_result(result: dict):
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]")

    data = json.loads(DATA_FILE.read_text())
    data.append(result)
    DATA_FILE.write_text(json.dumps(data, indent=2))


def load_results():
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text())

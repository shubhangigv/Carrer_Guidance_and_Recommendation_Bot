"""Read-only inventory of the O*NET text database.

Prints every file with its row and column count, and saves the full
column list to docs/onet_inventory.csv. It never modifies data/raw/.
"""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ONET_DIR = PROJECT_ROOT / "data" / "raw" / "onet"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "onet_inventory.csv"


def main() -> None:
    files = sorted(ONET_DIR.rglob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt files found under {ONET_DIR} - did you unzip it?")

    rows = []
    for path in files:
        try:
            # O*NET text files are tab-separated; dtype=str keeps codes like 15-2051.00 intact
            df = pd.read_csv(path, sep="\t", dtype=str, encoding="utf-8")
            rows.append({"file": path.name, "rows": len(df), "cols": df.shape[1],
                         "columns": " | ".join(df.columns)})
        except Exception as err:  # report the file instead of crashing
            rows.append({"file": path.name, "rows": None, "cols": None,
                         "columns": f"COULD NOT READ: {err}"})

    summary = pd.DataFrame(rows)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_FILE, index=False)

    print(summary[["file", "rows", "cols"]].to_string(index=False))
    print(f"\n{len(files)} files found. Column details saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

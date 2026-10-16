"""Make O*NET careers suitable for Indian students: short job titles and an India filter.

1. Short titles. O*NET's official titles are long US category names
   ("Entertainment and Recreation Managers, Except Gambling"). For each career we show:
     a) the common title O*NET itself shows students on My Next Move
        (`Sample of Reported Titles.txt`, rows with "Shown in My Next Move" = Y), choosing the one
        that shares most words with the official title (then the shortest), or
     b) if that file or its columns are missing, the official title with the US category
        wording trimmed: ", Except ...", ", All Other", ", Including ..." and "(...)".
   The official title is kept everywhere as well (details page, database, experiments).

2. India filter. config/india_exclusions.csv lists careers that do not apply in India
   (e.g. gambling jobs). Each row is a rule with a written reason, so the team can review
   and extend it. Excluded careers are removed from data["codes"], so they are never
   recommended or offered as alternatives; search still finds them and shows the reason.

Nothing here changes the scoring. Use apply_local_rules(data, onet_dir) after loading O*NET.
"""
import csv
import re
from pathlib import Path

import pandas as pd

from ml.baseline_recommender import _read

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCLUSIONS_FILE = PROJECT_ROOT / "config" / "india_exclusions.csv"

# Trailing US category wording, removed for the fallback short title.
_TRIM = [r",\s*Except\b.*$", r",\s*All Other\b.*$", r",\s*Including\b.*$", r"\s*\([^)]*\)"]


def clean_title(title):
    """Official title without US category wording: 'X, Except Y' -> 'X', 'X, All Other' -> 'X'."""
    out = str(title)
    for pattern in _TRIM:
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    return out.strip(" ,") or str(title)


def _stems(text):
    """Lower-case word stems (first 5 letters), so 'Managers' and 'Manager' match."""
    return {w[:5] for w in re.findall(r"[a-z]+", str(text).lower()) if len(w) > 2}


def pick_short_title(official, candidates):
    """The candidate sharing most words with the official title, then the shortest.
    Falls back to clean_title(official) when there are no candidates."""
    candidates = [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
    if not candidates:
        return clean_title(official)
    stems = _stems(clean_title(official))
    return min(candidates, key=lambda c: (-len(stems & _stems(c)), len(c), c))


def _my_next_move_titles(onet_dir):
    """{code: [titles shown in My Next Move]} or {} plus a message saying what was used."""
    try:
        df = _read(onet_dir, "Sample of Reported Titles.txt")
    except FileNotFoundError:
        return {}, "Sample of Reported Titles.txt: not found; short titles trimmed from official titles"
    title_col = next((c for c in df.columns if "reported" in c.lower() and "title" in c.lower()), None)
    shown_col = next((c for c in df.columns if "next move" in c.lower()), None)
    if "O*NET-SOC Code" not in df.columns or title_col is None:
        return {}, f"Sample of Reported Titles.txt: columns not usable {list(df.columns)}; titles trimmed instead"
    if shown_col is not None:
        df = df[df[shown_col].astype(str).str.strip().str.upper() == "Y"]
    used = f"'{title_col}'" + (f" where '{shown_col}' = Y" if shown_col else " (no My Next Move flag column)")
    return df.groupby("O*NET-SOC Code")[title_col].apply(list).to_dict(), \
        f"Sample of Reported Titles.txt: short titles from {used}"


def short_titles(data, onet_dir=None):
    """pandas Series code -> short display title, for every occupation."""
    found, info = _my_next_move_titles(onet_dir) if onet_dir is not None else ({}, "no O*NET folder; titles trimmed")
    data.setdefault("extras_info", []).append(info)
    official = data["occupations"]["Title"]
    return pd.Series({code: pick_short_title(t, found.get(code, [])) for code, t in official.items()})


def load_exclusions(path=EXCLUSIONS_FILE):
    """Rows of config/india_exclusions.csv: rule (code | title_contains), value, reason."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("rule") or "").strip() and not r["rule"].startswith("#")]
    for r in rows:
        if r["rule"].strip() not in ("code", "title_contains"):
            raise ValueError(f"{path}: unknown rule {r['rule']!r} (use 'code' or 'title_contains')")
    return rows


def excluded_careers(data, rules):
    """{code: reason}. title_contains is checked on the trimmed title, so
    'Entertainment and Recreation Managers, Except Gambling' does NOT match 'gambling'."""
    out = {}
    for code, title in data["occupations"]["Title"].items():
        trimmed = clean_title(title).lower()
        for r in rules:
            rule, value = r["rule"].strip(), r["value"].strip()
            if (rule == "code" and code == value) or (rule == "title_contains" and value.lower() in trimmed):
                out[code] = r["reason"].strip()
                break
    return out


def apply_local_rules(data, onet_dir=None, exclusions_path=EXCLUSIONS_FILE):
    """Add data["short_title"] and data["excluded"] ({code: reason}); drop excluded careers from data["codes"]."""
    data["short_title"] = short_titles(data, onet_dir)
    data["excluded"] = excluded_careers(data, load_exclusions(exclusions_path))
    data["codes"] = data["codes"].difference(list(data["excluded"]), sort=False)
    data["extras_info"].append(f"{exclusions_path.name if hasattr(exclusions_path, 'name') else exclusions_path}: "
                               f"{len(data['excluded'])} careers excluded for India")
    return data

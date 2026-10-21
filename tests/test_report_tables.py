"""experiments/report_tables.py builds the report tables from the committed results files."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import report_tables  # noqa: E402


def test_tables_are_built_from_the_results_files(tmp_path):
    out = report_tables.main(["--out", str(tmp_path / "tables.md")])
    text = out.read_text(encoding="utf-8")
    assert "Table 1." in text and "Hit@5" in text
    assert "do not edit by hand" in text


def test_missing_files_are_reported_not_invented(tmp_path, monkeypatch):
    monkeypatch.setattr(report_tables, "RES", tmp_path / "no_results")
    text = report_tables.main(["--out", str(tmp_path / "t.md")]).read_text(encoding="utf-8")
    assert "Table 1." not in text and "not available yet" in text

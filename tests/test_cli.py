"""Regression tests for CLI safety guarantees."""

import json
from pathlib import Path

from click.testing import CliRunner

from bitmerger.cli import cli


def test_batch_edit_in_place_captures_original_before_write(tmp_path: Path) -> None:
    vault = tmp_path / "vault.json"
    original = {
        "items": [{"id": "item-1", "type": 1, "name": "Old", "login": {"username": "alice", "password": "pw", "uris": []}}],
        "folders": [],
    }
    vault.write_text(json.dumps(original), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["batch-edit", str(vault), "-o", str(vault), "--search", "name:Old", "--field", "name", "--value", "New", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(vault.read_text(encoding="utf-8"))["items"][0]["name"] == "New"
    backups = list(tmp_path.glob("vault.original.*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["items"][0]["name"] == "Old"

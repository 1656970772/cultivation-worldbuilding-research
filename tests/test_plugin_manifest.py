import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_plugin_manifest_uses_official_layout():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "cultivation-worldbuilding-research"
    assert manifest["skills"] == "./skills/"
    assert manifest["author"]["name"]
    assert manifest["interface"]["displayName"]
    assert manifest["interface"]["shortDescription"]
    assert manifest["interface"]["longDescription"]
    assert manifest["interface"]["developerName"]
    assert manifest["interface"]["category"] == "Productivity"
    assert "Read" in manifest["interface"]["capabilities"]

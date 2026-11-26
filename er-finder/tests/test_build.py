import json
import shutil
import subprocess
from pathlib import Path

import build
import pytest

HERE = Path(__file__).resolve().parent


def test_compact_grid_roundtrip(tmp_path):
    deg = 1 / 120
    finder = {
        "built": "b",
        "er_source": "provisional",
        "cell_deg": deg,
        "targets": [{"name": "권역", "tiers": ["regional"]}, {"name": "아무 곳", "tiers": ["regional", "other"]}],
        "ers": [["가", 36.0, 129.0, "regional"], ["나", 36.1, 129.1, "other"]],
        "cells": [
            [round((4400 + 0.5) * deg, 4), round((15400 + 0.5) * deg, 4), 25.5, 0, 7.2, 1],
            [round((4401 + 0.5) * deg, 4), round((15403 + 0.5) * deg, 4), None, None, 4.0, 1],
        ],
    }
    g = build.compact(finder)
    assert (g["i0"], g["j0"], g["stride"]) == (4400, 15400, 6)
    assert g["cells"] == [0, 0, 255, 0, 72, 1, 1, 3, -1, -1, 40, 1]
    assert g["ers"][0] == ["가", 36.0, 129.0, "regional", "권역응급의료센터"]


def test_latest_beds_picks_last_snapshot(tmp_path):
    (tmp_path / "2026-11.csv").write_text(
        "dutyName,hvec,hvidate,collected_at\n가병원,3,20261125090000,2026-11-25 09:00\n가병원,1,20261125100000,2026-11-25 10:00\n나병원,0,20261125100000,2026-11-25 10:00\n",
        encoding="utf-8",
    )
    b = build.latest_beds(tmp_path)
    assert b["collected_at"] == "2026-11-25 10:00" and b["by_name"]["가병원"]["hvec"] == "1" and len(b["by_name"]) == 2
    assert build.latest_beds(tmp_path / "none") is None


def test_build_from_er_access_output(tmp_path):
    if not build.SRC.exists():
        pytest.skip("er-access/docs/finder.json 없음")
    st = build.build(out=tmp_path)
    g = json.loads((tmp_path / "grid.json").read_text(encoding="utf-8"))
    assert st["cells"] == len(g["cells"]) // g["stride"] and g["beds"] is False


def test_pwa_files_are_consistent():
    docs = HERE.parent / "docs"
    m = json.loads((docs / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icon in m["icons"]:
        assert (docs / icon["src"]).exists()
    sw = (docs / "sw.js").read_text(encoding="utf-8")
    for f in ["index.html", "finder.js", "grid.json", "manifest.webmanifest"]:
        assert f"'{f}'" in sw and (docs / f).exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_finder_js_with_node():
    r = subprocess.run(["node", "--test", str(HERE / "finder.test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]

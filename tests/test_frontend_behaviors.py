from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run_node_test(script_name: str) -> None:
    script_path = ROOT / "js" / script_name
    result = subprocess.run(["node", str(script_path)], capture_output=True, text=True)
    if result.returncode != 0:
        output = result.stdout + "\n" + result.stderr
        raise AssertionError(f"Node test {script_name} failed:\n{output.strip()}")


def test_dirty_guard_js() -> None:
    _run_node_test("dirty_guard.test.js")


def test_auto_filter_js() -> None:
    _run_node_test("auto_filter.test.js")

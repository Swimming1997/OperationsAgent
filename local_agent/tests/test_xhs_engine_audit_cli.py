import subprocess
import sys
from pathlib import Path


LOCAL_AGENT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_capabilities_runs_without_xhs_network():
    result = subprocess.run(
        [sys.executable, "scripts/xhs_engine_audit.py", "--surface", "capabilities"],
        cwd=LOCAL_AGENT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "xhs.feed.home_recommend" in result.stdout
    assert "summary.json" in result.stdout

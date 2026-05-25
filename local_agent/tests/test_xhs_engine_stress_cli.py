import subprocess
import sys
from pathlib import Path


def test_stress_cli_writes_ndjson(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "stress_xhs_engine.py"
    result = subprocess.run(
        [sys.executable, str(script), "--keywords", "SCI", "--rounds", "1", "--max-items", "1", "--output-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0
    output = Path(result.stdout.strip())
    assert output.exists()
    assert "xhs_engine_stress_" in output.name

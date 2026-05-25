import subprocess
import sys
from pathlib import Path


def test_bench_cli_writes_ndjson(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "bench_xhs_engine.py"
    result = subprocess.run(
        [sys.executable, str(script), "--keywords", "SCI", "--max-items", "1", "--output-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    output = Path(result.stdout.strip())
    assert output.exists()
    assert "xhs_engine_bench_" in output.name

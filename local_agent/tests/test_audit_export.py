import json
import zipfile

from local_agent_runtime.audit.logger import EngineAuditLogger
from local_agent_runtime.audit.models import EngineAuditRecord, EngineAuditRunSummary


def test_engine_audit_export_bundle_contains_manifest_and_outputs(tmp_path):
    logger = EngineAuditLogger(project_root=tmp_path, run_id="20260620_export001")
    summary = EngineAuditRunSummary(
        "20260620_export001",
        [EngineAuditRecord("xhs.feed.home_recommend", "homefeed", "ok")],
        12.0,
    )
    logger.write_records(summary.records)
    logger.write_summary(summary)

    bundle = logger.export_bundle()

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        manifest_name = "engine_audit_20260620_export001.manifest.json"
        assert manifest_name in names
        assert logger.summary_json_path.name in names
        manifest = json.loads(archive.read(manifest_name))
        assert manifest["run_id"] == "20260620_export001"
        assert logger.summary_md_path.name in manifest["files"]

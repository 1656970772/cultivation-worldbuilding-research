import importlib
import hashlib
import json
import textwrap
from pathlib import Path

import pytest


def _module():
    try:
        return importlib.import_module("scripts.pipeline.finalize_reviewed")
    except ModuleNotFoundError as exc:
        pytest.fail(f"finalize_reviewed module is required: {exc}")


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
    )


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_entry(review_id: str = "review-001", name: str = "Alpha") -> dict:
    return {
        "review_id": review_id,
        "name": name,
        "aliases": [],
        "fields": {"Name": name, "Effect": "unknown"},
        "source_spans": [
            {
                "segment_id": "seg-001",
                "start_char": 0,
                "end_char": len(name),
                "line": 1,
                "summary": f"{name} appears.",
            }
        ],
    }


def _decision(
    review_id: str = "review-001",
    decision: str = "confirmed",
    name: str = "Alpha",
) -> dict:
    return {
        "review_id": review_id,
        "decision": decision,
        "name": name,
        "fields": {"Name": name, "Effect": "restores energy"},
        "notes": "enough evidence",
    }


def _write_inputs(tmp_path: Path, *, decision_value: str = "confirmed") -> dict[str, Path]:
    review_pack = tmp_path / "review-pack.jsonl"
    decisions = tmp_path / "review-decisions.jsonl"
    curation = _write_yaml(
        tmp_path / "curation.yaml",
        """
        work_title: Test Work
        subject_type: Entity
        fields:
          required: [Name, Effect]
          unknown_text: unknown
        decision_validation:
          allowed_decisions: [confirmed, rejected, needs-review]
          require_all_review_ids: true
          require_confirmed_source_spans: true
          required_field_policy: fill_unknown
        confirmed_audit:
          require_source_spans: true
          check_markdown_row_count: true
        """,
    )
    default_config = _write_yaml(
        tmp_path / "default-config.yaml",
        """
        output:
          output_name_pattern: "{work_title}-{subject_type}.md"
          report_title_pattern: "{work_title} {subject_type}"
          evidence_in_final_report: false
        """,
    )
    expected = _write_yaml(
        tmp_path / "expected.yaml",
        """
        required_columns: [Name, Effect]
        expected_present: [Alpha]
        """,
    )
    _write_jsonl(review_pack, [_review_entry()])
    _write_jsonl(decisions, [_decision(decision=decision_value)])
    return {
        "review_pack": review_pack,
        "decisions": decisions,
        "curation": curation,
        "default_config": default_config,
        "expected": expected,
    }


def _finalize(tmp_path: Path, **overrides):
    module = _module()
    paths = _write_inputs(tmp_path)
    args = {
        "workdir": tmp_path,
        "review_pack": paths["review_pack"],
        "decisions": paths["decisions"],
        "curation": paths["curation"],
        "default_config": paths["default_config"],
        "expected": paths["expected"],
        "template": None,
        "route": None,
        "output_report": None,
        "run_manifest": tmp_path / "run-manifest.json",
    }
    args.update(overrides)
    return module.finalize_reviewed(**args)


def test_finalize_success_writes_all_outputs_and_run_manifest(tmp_path):
    result = _finalize(tmp_path)

    confirmed_path = tmp_path / "confirmed-items.json"
    curation_report_path = tmp_path / "curation-report.json"
    report_path = tmp_path / "Test Work-Entity.md"
    validation_path = tmp_path / "validation-report.json"
    audit_path = tmp_path / "confirmed-audit-report.json"
    manifest_path = tmp_path / "run-manifest.json"

    assert result["passed"] is True
    assert result["run_manifest"] == str(manifest_path)
    assert result["confirmed"] == str(confirmed_path)
    assert result["report"] == str(report_path)
    assert result["audit"] == str(audit_path)
    for path in [
        tmp_path / "decision-validation-report.json",
        confirmed_path,
        curation_report_path,
        report_path,
        validation_path,
        audit_path,
        manifest_path,
    ]:
        assert path.exists(), path

    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    assert confirmed["items"][0]["name"] == "Alpha"
    assert "Alpha" in report_path.read_text(encoding="utf-8")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["passed"] is True
    assert [step["name"] for step in manifest["steps"]] == [
        "validate-decisions",
        "merge-reviewed",
        "render",
        "validate",
        "audit-confirmed",
    ]
    assert all(step["passed"] for step in manifest["steps"])
    assert manifest["inputs"]["review_pack"]["sha256"]
    assert manifest["inputs"]["decisions"]["sha256"]
    assert manifest["outputs"]["confirmed"]["path"] == str(confirmed_path)
    assert manifest["outputs"]["report"]["path"] == str(report_path)
    expected_output_paths = {
        "decision_validation": tmp_path / "decision-validation-report.json",
        "confirmed": confirmed_path,
        "curation_report": curation_report_path,
        "report": report_path,
        "validation": validation_path,
        "audit": audit_path,
    }
    for name, path in expected_output_paths.items():
        record = manifest["outputs"][name]
        assert record == {
            "path": str(path),
            "exists": True,
            "produced": True,
            "sha256": _sha256(path),
        }
        assert manifest["checksums"]["outputs"][name] == _sha256(path)
    assert manifest["outputs"]["run_manifest"] == {
        "path": str(manifest_path),
        "exists": True,
        "sha256": None,
    }
    assert "run_manifest" not in manifest["checksums"]["outputs"]
    assert manifest["counts"]["review_entries"] == 1
    assert manifest["counts"]["decisions"] == 1
    assert manifest["counts"]["confirmed_decisions"] == 1
    assert manifest["counts"]["confirmed_items"] == 1
    assert manifest["counts"]["blocking_errors"] == 0
    assert manifest["counts"]["warnings"] == 0


def test_finalize_stops_before_merge_when_decisions_invalid(tmp_path):
    module = _module()
    paths = _write_inputs(tmp_path, decision_value="maybe")
    result = module.finalize_reviewed(
        workdir=tmp_path,
        review_pack=paths["review_pack"],
        decisions=paths["decisions"],
        curation=paths["curation"],
        default_config=paths["default_config"],
        expected=paths["expected"],
        template=None,
        route=None,
        output_report=None,
        run_manifest=tmp_path / "run-manifest.json",
    )

    assert result["passed"] is False
    assert result["failed_step"] == "validate-decisions"
    assert result["confirmed"] is None
    assert result["report"] is None
    assert result["audit"] is None
    assert (tmp_path / "decision-validation-report.json").exists()
    assert not (tmp_path / "confirmed-items.json").exists()
    assert not (tmp_path / "curation-report.json").exists()
    assert not (tmp_path / "Test Work-Entity.md").exists()
    assert not (tmp_path / "validation-report.json").exists()
    assert not (tmp_path / "confirmed-audit-report.json").exists()

    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["passed"] is False
    assert manifest["failed_step"] == "validate-decisions"
    assert [step["name"] for step in manifest["steps"]] == ["validate-decisions"]
    assert manifest["steps"][0]["passed"] is False
    assert manifest["outputs"]["decision_validation"]["exists"] is True
    assert manifest["outputs"]["decision_validation"]["sha256"] == _sha256(
        tmp_path / "decision-validation-report.json"
    )
    assert manifest["outputs"]["confirmed"]["exists"] is False
    assert manifest["outputs"]["confirmed"]["sha256"] is None
    assert manifest["outputs"]["curation_report"]["exists"] is False
    assert manifest["outputs"]["audit"]["exists"] is False
    assert manifest["outputs"]["run_manifest"] == {
        "path": str(tmp_path / "run-manifest.json"),
        "exists": True,
        "sha256": None,
    }
    assert manifest["counts"]["blocking_errors"] == 1


def test_finalize_invalid_decisions_result_ignores_stale_artifacts(tmp_path, monkeypatch):
    module = _module()
    paths = _write_inputs(tmp_path, decision_value="maybe")
    stale_report = tmp_path / "stale-report.md"
    for path in [
        tmp_path / "confirmed-items.json",
        stale_report,
        tmp_path / "confirmed-audit-report.json",
    ]:
        path.write_text("stale\n", encoding="utf-8")
    stale_paths = {
        tmp_path / "confirmed-items.json",
        stale_report,
        tmp_path / "confirmed-audit-report.json",
    }
    original_sha256 = module._sha256

    def fail_for_stale_unproduced(path):
        path = Path(path)
        if path in stale_paths:
            pytest.fail(f"unproduced stale output was checksummed: {path}")
        return original_sha256(path)

    monkeypatch.setattr(module, "_sha256", fail_for_stale_unproduced)

    result = module.finalize_reviewed(
        workdir=tmp_path,
        review_pack=paths["review_pack"],
        decisions=paths["decisions"],
        curation=paths["curation"],
        default_config=paths["default_config"],
        expected=paths["expected"],
        template=None,
        route=None,
        output_report=stale_report,
        run_manifest=tmp_path / "run-manifest.json",
    )

    assert result["passed"] is False
    assert result["failed_step"] == "validate-decisions"
    assert result["confirmed"] is None
    assert result["report"] is None
    assert result["audit"] is None

    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["failed_step"] == "validate-decisions"
    assert manifest["outputs"]["decision_validation"]["produced"] is True
    assert manifest["outputs"]["decision_validation"]["sha256"] == _sha256(
        tmp_path / "decision-validation-report.json"
    )
    for name, path in {
        "confirmed": tmp_path / "confirmed-items.json",
        "report": stale_report,
        "audit": tmp_path / "confirmed-audit-report.json",
    }.items():
        record = manifest["outputs"][name]
        assert record["path"] == str(path)
        assert record["exists"] is True
        assert record["produced"] is False
        assert record["sha256"] is None
        assert name not in manifest["checksums"]["outputs"]


def test_finalize_malformed_route_returns_structured_failure_manifest(tmp_path):
    module = _module()
    paths = _write_inputs(tmp_path)
    route = tmp_path / "route-report.json"
    route.write_text("{not-json", encoding="utf-8")

    result = module.finalize_reviewed(
        workdir=tmp_path,
        review_pack=paths["review_pack"],
        decisions=paths["decisions"],
        curation=paths["curation"],
        default_config=paths["default_config"],
        expected=paths["expected"],
        template=None,
        route=route,
        output_report=None,
        run_manifest=tmp_path / "run-manifest.json",
    )

    assert result["passed"] is False
    assert result["failed_step"] == "prepare"
    assert result["confirmed"] is None
    assert result["report"] is None
    assert result["audit"] is None
    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["passed"] is False
    assert manifest["failed_step"] == "prepare"
    assert len(manifest["steps"]) == 1
    step = manifest["steps"][0]
    assert step["name"] == "prepare"
    assert step["passed"] is False
    assert step["counts"] == {"blocking_errors": 1, "warnings": 0}
    assert step["blocking_errors"][0]["type"] == "prepare_failed"
    assert "Expecting property name" in step["blocking_errors"][0]["message"]
    assert step["warnings"] == []
    assert manifest["outputs"]["confirmed"]["exists"] is False
    assert manifest["outputs"]["audit"]["exists"] is False
    assert manifest["outputs"]["run_manifest"] == {
        "path": str(tmp_path / "run-manifest.json"),
        "exists": True,
        "sha256": None,
    }


def test_finalize_invalid_confirmed_audit_config_writes_structured_failure_manifest(
    tmp_path,
):
    module = _module()
    paths = _write_inputs(tmp_path)
    paths["curation"].write_text(
        textwrap.dedent(
            """
            work_title: Test Work
            subject_type: Entity
            fields:
              required: [Name, Effect]
              unknown_text: unknown
            decision_validation:
              allowed_decisions: [confirmed, rejected, needs-review]
              require_all_review_ids: true
              require_confirmed_source_spans: true
              required_field_policy: fill_unknown
            confirmed_audit: []
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = module.finalize_reviewed(
        workdir=tmp_path,
        review_pack=paths["review_pack"],
        decisions=paths["decisions"],
        curation=paths["curation"],
        default_config=paths["default_config"],
        expected=paths["expected"],
        template=None,
        route=None,
        output_report=None,
        run_manifest=tmp_path / "run-manifest.json",
    )

    audit_path = tmp_path / "confirmed-audit-report.json"
    manifest_path = tmp_path / "run-manifest.json"
    assert result["passed"] is False
    assert result["failed_step"] == "audit-confirmed"
    assert result["audit"] == str(audit_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["passed"] is False
    assert audit["counts"] == {"blocking_errors": 1, "warnings": 0}
    assert audit["blocking_errors"][0]["type"] == "audit-confirmed_failed"
    assert "confirmed_audit must be a mapping" in audit["blocking_errors"][0]["message"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["passed"] is False
    assert manifest["failed_step"] == "audit-confirmed"
    assert [step["name"] for step in manifest["steps"]] == [
        "validate-decisions",
        "merge-reviewed",
        "render",
        "validate",
        "audit-confirmed",
    ]
    assert manifest["steps"][-1]["passed"] is False
    assert manifest["outputs"]["audit"] == {
        "path": str(audit_path),
        "exists": True,
        "produced": True,
        "sha256": _sha256(audit_path),
    }
    assert manifest["checksums"]["outputs"]["audit"] == _sha256(audit_path)
    assert manifest["counts"]["blocking_errors"] == 1


def test_finalize_validation_merge_preserves_report_blocking_errors():
    module = _module()

    merged = module.merge_validation_results(
        {
            "passed": False,
            "blocking_errors": [{"type": "missing_required_columns"}],
            "coverage_warnings": {"report_warning": ["kept"]},
        },
        {
            "passed": True,
            "blocking_errors": [],
            "coverage_warnings": {"expected_present_missing": ["Missing"]},
        },
    )

    assert merged["passed"] is False
    assert merged["blocking_errors"] == [{"type": "missing_required_columns"}]
    assert merged["coverage_warnings"] == {
        "report_warning": ["kept"],
        "expected_present_missing": ["Missing"],
    }


def test_finalize_template_recorded_but_not_passed_to_render_report(tmp_path, monkeypatch):
    module = _module()
    template = tmp_path / "template.md"
    template.write_text("# Template\n", encoding="utf-8")
    unexpected_kwargs = {}

    def fake_render_report(confirmed, output_path, route_config=None, default_config=None, **kwargs):
        unexpected_kwargs.update(kwargs)
        output_path.write_text(
            "\n".join(
                [
                    "# Fake",
                    "",
                    "| Name | Effect |",
                    "| --- | --- |",
                    "| Alpha | restores energy |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(module, "render_report", fake_render_report)

    result = _finalize(tmp_path, template=template)

    assert result["passed"] is True
    assert unexpected_kwargs == {}
    manifest = json.loads((tmp_path / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["inputs"]["template"]["path"] == str(template)


def test_finalize_does_not_reread_review_pack_or_decisions(tmp_path, monkeypatch):
    module = _module()
    paths = _write_inputs(tmp_path)
    read_counts = {"review_pack": 0, "decisions": 0}
    original_read_jsonl_objects = module.read_jsonl_objects
    original_load_decision_records = module.load_decision_records

    def counted_read_jsonl_objects(path):
        if path == paths["review_pack"]:
            read_counts["review_pack"] += 1
        return original_read_jsonl_objects(path)

    def counted_load_decision_records(path):
        if path == paths["decisions"]:
            read_counts["decisions"] += 1
        return original_load_decision_records(path)

    monkeypatch.setattr(module, "read_jsonl_objects", counted_read_jsonl_objects)
    monkeypatch.setattr(module, "load_decision_records", counted_load_decision_records)
    monkeypatch.setattr(
        module,
        "read_decisions_jsonl",
        lambda path: pytest.fail("finalize must reuse decision_rows"),
        raising=False,
    )

    result = module.finalize_reviewed(
        workdir=tmp_path,
        review_pack=paths["review_pack"],
        decisions=paths["decisions"],
        curation=paths["curation"],
        default_config=paths["default_config"],
        expected=paths["expected"],
        template=None,
        route=None,
        output_report=None,
        run_manifest=tmp_path / "run-manifest.json",
    )

    assert result["passed"] is True
    assert read_counts == {"review_pack": 1, "decisions": 1}

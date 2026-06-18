import json
from pathlib import Path

from langextract import data as lx_data

from scripts.pipeline.extraction_runner import run_extraction


class FakeConfig:
    provider_kwargs = {"api_key": "key", "base_url": "https://example/v1"}


def test_run_extraction_filters_ungrounded_records_and_writes_summary(tmp_path: Path):
    source = tmp_path / "凡人修仙传.txt"
    source.write_text("韩立服下聚气丹。", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 |\n| --- | --- |\n| 聚气丹 | 增加真气 |\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "encoding:",
                "  fallbacks: [utf-8]",
                "extraction:",
                "  model_id: MiniMax-M2.7",
                "  base_url: https://example/v1",
                "  extraction_passes: 1",
                "  max_workers: 1",
                "  max_char_buffer: 1000",
                "  generate_visualization: false",
                "  grounded_jsonl_name: grounded-extractions.jsonl",
                "  merged_json_name: merged-extractions.json",
                "  run_summary_name: run-summary.json",
                "  visualization_html_name: visualization.html",
                "  report_name_pattern: custom-{source_stem}-{template_stem}.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def fake_extract(**kwargs):
        calls.append(kwargs)
        return lx_data.AnnotatedDocument(
            text=kwargs["text_or_documents"],
            extractions=[
                lx_data.Extraction(
                    extraction_class="丹药",
                    extraction_text="聚气丹",
                    char_interval=lx_data.CharInterval(start_pos=4, end_pos=7),
                    attributes={"丹药名称": "聚气丹", "功效": "增加真气"},
                ),
                lx_data.Extraction(
                    extraction_class="丹药",
                    extraction_text="示例丹",
                    char_interval=None,
                    attributes={"丹药名称": "示例丹"},
                ),
            ],
        )
    visualization_calls = []

    def fake_visualize(**kwargs):
        visualization_calls.append(kwargs)
        kwargs["output_path"].write_text("<html></html>\n", encoding="utf-8")

    summary = run_extraction(
        template_path=template,
        source_file=source,
        output_dir=tmp_path / "out",
        config_path=config,
        extract_fn=fake_extract,
        build_model_config_fn=lambda **kwargs: FakeConfig(),
        compose_fn=lambda **kwargs: "# report\n",
        extraction_passes=2,
        max_workers=3,
        max_char_buffer=10,
        generate_visualization=True,
        visualize_fn=fake_visualize,
    )

    assert calls[0]["extraction_passes"] == 2
    assert calls[0]["max_workers"] == 3
    assert calls[0]["max_char_buffer"] == 10
    grounded = [
        json.loads(line)
        for line in (tmp_path / "out" / "grounded-extractions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["extraction_text"] for item in grounded] == ["聚气丹"]
    assert summary["counts"]["raw_extractions"] == 2
    assert summary["counts"]["grounded_extractions"] == 1
    assert summary["elapsed_seconds"] >= 0
    assert visualization_calls
    assert Path(summary["outputs"]["visualization_html"]).exists()
    assert (tmp_path / "out" / "custom-凡人修仙传-丹药分析.md").read_text(encoding="utf-8") == "# report\n"


def test_run_extraction_dry_run_records_limit_without_calling_model(tmp_path: Path):
    source = tmp_path / "凡人修仙传.txt"
    source.write_text("韩立服下聚气丹。" * 20, encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")

    def fail_extract(**kwargs):
        raise AssertionError("dry-run must not call extract")

    summary = run_extraction(
        template_path=template,
        source_file=source,
        output_dir=tmp_path / "out",
        extract_fn=fail_extract,
        build_model_config_fn=lambda **kwargs: FakeConfig(),
        dry_run=True,
        limit_chars=12,
        max_char_buffer=5,
    )

    assert summary["dry_run"] is True
    assert summary["elapsed_seconds"] >= 0
    assert summary["source"]["truncated"] is True
    assert summary["source"]["limit_chars"] == 12
    assert summary["estimates"]["chunk_count"] == 3
    assert summary["estimates"]["composition_call_count"] == 1
    assert summary["estimates"]["total_call_count"] == 10


def test_run_extraction_requires_examples_before_model_call(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("没有模板示例。", encoding="utf-8")
    template = tmp_path / "自由模板.md"
    template.write_text("# 自由模板\n请整理资料。\n", encoding="utf-8")

    def fail_extract(**kwargs):
        raise AssertionError("missing examples should fail before model call")

    try:
        run_extraction(
            template_path=template,
            source_file=source,
            output_dir=tmp_path / "out",
            extract_fn=fail_extract,
            build_model_config_fn=lambda **kwargs: FakeConfig(),
            dry_run=False,
        )
    except ValueError as exc:
        assert "few-shot examples" in str(exc)
    else:
        raise AssertionError("expected ValueError")

from scripts.pipeline.renderer import render_report


def test_render_case_collection():
    report = render_report(
        title="案例集",
        entries=[{"name": "夺宝冲突", "fields": {"起因": "秘境开启", "后果": "宗门结怨"}}],
        route={"report_shape": "case_collection", "render_blocks": ["case_index", "cases"]},
    )

    assert "## 案例索引" in report
    assert "### 夺宝冲突" in report


def test_render_chain_strategies():
    for shape, expected in [
        ("process_chain", "## 流程步骤"),
        ("decision_chain", "## 决策节点"),
        ("relationship_chain", "## 关系链"),
        ("profession_workflow", "## 职业闭环"),
    ]:
        report = render_report(
            title="链式报告",
            entries=[{"name": "节点一", "fields": {"说明": "证据确认"}}],
            route={"report_shape": shape},
        )
        assert expected in report


def test_file_render_uses_shape_strategy_when_tables_are_forbidden(tmp_path):
    confirmed = {
        "work_title": "测试作品",
        "items": [
            {
                "status": "confirmed",
                "name": "青木谷",
                "fields": {"名称": "青木谷", "类型": "区域", "概览": "灵植聚集"},
                "source_spans": [
                    {"segment_id": "seg-1", "line": 1, "summary": "青木谷灵植聚集"}
                ],
            }
        ],
    }
    out = tmp_path / "报告.md"

    render_report(
        confirmed,
        out,
        route_config={
            "report_shape": "overview_plus_cards",
            "forbidden_output_modes": ["表格"],
        },
    )

    report = out.read_text(encoding="utf-8")
    assert "| 名称 | 类型 | 概览 |" not in report
    assert "## 条目详情" in report
    assert "### 青木谷" in report

from scripts.pipeline.validator import validate_report


def test_forbidden_table_mode_fails_when_table_present():
    result = validate_report(
        "# 报告\n\n| 名称 | 说明 |\n| --- | --- |\n| A | B |\n",
        route={
            "forbidden_output_modes": ["table"],
            "validation_rules": {"forbidden_output_mode_policy": "fail"},
        },
    )

    assert result.ok is False
    assert "forbidden output mode: table" in result.messages


def test_required_fields_apply_to_cards_and_chains():
    result = validate_report(
        "# 报告\n\n### 青竹蜂云剑\n- 类型：法宝\n",
        route={"required_fields": ["名称", "类型"], "report_shape": "cards_only"},
    )

    assert result.ok is False
    assert "missing required field: 名称" in result.messages

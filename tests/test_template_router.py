from pathlib import Path

import pytest

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_router import route_template


ROOT = Path(__file__).resolve().parents[1]


def test_routes_phase1_templates():
    route = route_template(ROOT / "assets" / "template-registry.yaml", Path("丹药分析模板.md"), "")
    assert route["primary_mode"] == "entity"
    assert route["rule_pack"] == "entity-medicine"
    assert route["subject_type"] == "丹药"
    assert route["output_name_pattern"] == "{work_title}丹药分析.md"
    assert route["report_title_pattern"] == "《{work_title}》{subject_type}分析"
    assert route["required_columns"] == [
        "丹药名称",
        "稀有度",
        "功效",
        "用途",
        "丹方",
        "炼制方式",
        "来源",
        "限制/副作用",
        "适用境界",
    ]


@pytest.mark.parametrize("content", ["false", "0", "null", ""])
def test_load_yaml_rejects_falsey_non_mapping_root(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="YAML root must be a mapping"):
        load_yaml(path)

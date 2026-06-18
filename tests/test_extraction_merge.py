from scripts.pipeline.extraction_merge import merge_extractions


def test_merge_extractions_deduplicates_by_identity_field_and_keeps_spans():
    records = [
        {
            "extraction_text": "聚气丹",
            "attributes": {"丹药名称": "聚气丹", "功效": "增加真气"},
            "char_interval": {"start_pos": 10, "end_pos": 13},
        },
        {
            "extraction_text": "聚气丹",
            "attributes": {"丹药名称": "聚气丹", "用途": "日常修炼"},
            "char_interval": {"start_pos": 100, "end_pos": 103},
        },
    ]

    merged = merge_extractions(records, identity_field="丹药名称")

    assert len(merged) == 1
    assert merged[0]["name"] == "聚气丹"
    assert merged[0]["fields"] == {
        "丹药名称": "聚气丹",
        "功效": "增加真气",
        "用途": "日常修炼",
    }
    assert merged[0]["source_spans"] == [
        {"start_char": 10, "end_char": 13, "summary": "聚气丹"},
        {"start_char": 100, "end_char": 103, "summary": "聚气丹"},
    ]


def test_merge_extractions_normalizes_list_attributes():
    merged = merge_extractions(
        [
            {
                "extraction_text": "韩立关系链",
                "attributes": {"名称": "韩立关系链", "参与者": ["韩立", "南宫婉"]},
                "char_interval": {"start_pos": 1, "end_pos": 5},
            }
        ],
        identity_field="名称",
    )

    assert merged[0]["fields"]["参与者"] == "韩立、南宫婉"

---
name: project-goal-template-driven-generation
description: User's real goal for the cultivation-worldbuilding plugin — template-driven, per-template parallel agent doc generation
metadata:
  type: project
---

用户目标：给插件一个模板目录（如 `E:\AI_Projects\CultivationWorld\docs\世界观参考\模板`，38个模板）+ 小说原文目录（如 `...\凡人修仙传\凡人修仙传.txt`），插件自动按每个模板的规范产出对应分析文档，结果写回原文目录。

核心诉求：
1. **每个模板单独派一个 agent**，不要一个 agent 跑多个文档；多个文档分析**并行**跑。
2. 输出质量要达到人工撰写水准（参考已有的 `法宝妖兽丹药分析.md`），而不是当前 regex 抽取出的扁平候选名单。
3. 不要每次调用都直接覆盖已有文档（用户对当前结果不满意）。

关键技术现实（决定方案）：Python pipeline (`scripts/worldbuilding_pipeline.py` + `scripts/pipeline/*`) 本质是**正则后缀匹配的名词采集器**（`candidate_extractor.py`），不做语义理解。填字段（功效/丹方/来源等）的真正分析一直是设定由 LLM agent 在 review 阶段完成，但 SKILL.md 从未指示 agent 怎么做、也没并行编排。`assets/template-registry.yaml` 只覆盖 1 个模板（丹药），其余 37 个走不到注册表。模板本身（如 `丹药分析模板.md`）含「必须写什么」字段定义表、「前置声明」禁造规则、「推荐结构」输出骨架——这些是 agent 该读的契约。

三个已拍板决策（2026-06-18）：
1. **并行落地**：SKILL.md 写"每模板一 agent、并行、不串跑"约束；实际由调用方（用户在 Claude Code/Codex 一条消息发多个 Agent）并行。Python 只产 `batch-plan.json`，不在脚本里管 LLM 调用。
2. **覆盖策略**：默认**覆盖**；仅当用户明确说"增量/合并"时走 merge（读旧文档、保留高质量内容、只补缺/纠错/加遗漏）。需支持显式 `--mode merge|overwrite` 开关，默认 overwrite。
3. **形状映射**：`template_profile.py` 全自动从模板「推荐结构」推断形状/字段，零配置支持新模板；`framework-presets.yaml` 的 expected_files 映射仅兜底。

Codex 执行改动清单（按优先级）：
- P0 重写 `skills/extracting-worldbuilding/SKILL.md`：批量编排主流程 + 子agent标准prompt契约（注入单个模板全文+README元规则+原文路径+输出路径+禁造/三类标注约束）+ Python降级为辅助 + 质量参考样例(法宝妖兽丹药分析.md) + 覆盖默认/增量约束。
- P0 修 `framework-presets.yaml` expected_files = 真实38文件名+正确形状（兜底用）。
- P1 改 `template_profile.py`：推荐结构为形状/字段判定首要来源。
- P1 去掉 `template-registry.yaml` 丹药硬编码特化。
- P2 新增 `scripts/run_batch.ps1`：列模板→预生成framework→输出 batch-plan.json，带 mode merge|overwrite。
- P2 更新 tests：真实模板形状、batch-plan、覆盖模式。

Codex 已把方案展开成 `docs/优化方案-模板驱动并行生成.md`（TDD 实施计划，7 个 Task）。2026-06-18 审查并修正了 4 个会导致执行失败的硬错误：
1. BOM：真实模板全部带 UTF-8 BOM，`template_profile.py` 与 `batch_plan.py` 读模板/README 必须用 `utf-8-sig`（已加 Task 3 Step 0 + BOM 回归测试）。
2. Task 3 test2（config 兜底胜出）：临时目录缺 README.md → `_configured_report_shape` 不激活 → 断言 confidence==1.0 失败。已要求测试在 tmp_path 建 README.md。
3. Task 2/Task 3 冲突：方案原 `test_real_template_shapes` 同时断言「配置值==推断值」，但实测推断器对 5+ 模板（灵根体质血脉/记忆情绪/散修生存/宗门任务/妖兽与修士关系）与人工兜底表分歧。已改为：推断优先（符合用户意图），真实模板测试只断言「落到合法 shape」，不钉死具体 shape。
4. Task 4 registry 置空：已加全量回归步骤，核实真正读真实 registry 的消费者只有 2 处且都已处理。
修正均已用模拟脚本验证通过（3 个新单测 + 38 真实模板全部解析为合法 shape）。结论：可执行。

**2026-06-18 重大方向纠正（V1 作废，改 V2）**：用户硬要求"零遗漏"（如丹药一个都不能漏）。V1 让 subagent 直读 1500 万字大原文 → 触发 Lost-in-the-Middle 必漏，错误。用户给了参考资料 `E:\AI_Projects\修仙游戏调研\docs\参考资料\信息抽取`（LangExtract / LLM-IE / RAG / spaCy / Lost-in-the-Middle）。正确范式：**Python 切块 → 大模型逐块抽取（多趟 extraction_passes=3 + 并行）→ 对齐溯源 → 合并去重 → 大模型按模板成文**。抽取也是大模型做（非正则），Python 只做切块/对齐/合并机械活。
模型后端：**MiniMax-M2.7**，OpenAI 兼容口 `https://api.minimaxi.com/v1`（国内站；.io 国际站对此 key 返回 401）。实测 M2.7/M3/M2.5 可用，M2.7 带 think 思维链。key 已落 `.env` 并 gitignore（用户给的 key 已暴露在对话，建议轮换）。集成方式：LangExtract + `ModelConfig(provider="openai", base_url, api_key)`。
原文编码 gb18030；模板带 BOM 用 utf-8-sig。
验证范围：先跑 5 个代表模板（丹药/事件因果链/人物关系/功法/势力，覆盖 5 种形状），满意+成本可接受再铺 37 个。
新方案文档：[[docs/优化方案-V2-LangExtract零遗漏抽取.md]]。V1 文档 `docs/优化方案-模板驱动并行生成.md` 已作废。

---
name: extracting-worldbuilding
description: Use when extracting worldbuilding research from long fiction or game text with configurable templates, evidence packs, and Markdown report validation.
---

# Extracting Worldbuilding

本技能用于“模板目录 + 小说原文”的世界观研究生成。核心流程是模板驱动的并行编排：Python 生成 `batch-plan.json`，调用方根据 plan 派发多个 subagent，最终每个模板产出一篇 Markdown 文档。

## 批量模板编排主流程

输入：模板目录、原文目录、原文文件，可选 `Mode overwrite|merge`。

1. 列出模板目录下所有 `*.md`，排除 `README.md`。
2. 读取模板目录下的 `README.md` 作为全局元规则，并注入每个子任务。
3. 对每个模板创建一个独立任务；每个模板一个独立 subagent，只负责这一份模板对应的一篇文档。
4. 调用方在一条消息内并行派发这些 subagent。
5. 每篇结果写回原文目录，文件名 = 模板名删除“模板”二字，例如 `丹药分析模板.md` 写为 `丹药分析.md`。

强制约束：一模板一 agent；并行；禁止一个 agent 串跑多篇文档。

Python 脚本只生成 `batch-plan.json` 和每模板 framework 文件，不调用 LLM，不管理 API key，不管理并发，不替 subagent 撰写最终文档。

## 推荐入口

在 Windows 上优先使用批量入口：

```powershell
& 'C:\Users\Administrator\plugins\cultivation-worldbuilding-research\scripts\run_batch.ps1' `
  -TemplateDir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' `
  -SourceDir 'E:\AI_Projects\CultivationWorld\凡人修仙传' `
  -SourceFile 'E:\AI_Projects\CultivationWorld\凡人修仙传\凡人修仙传.txt' `
  -Mode overwrite
```

生成后读取原文目录下的 `batch-plan.json`，按 `items[].subagent_prompt` 并行派发 subagent。

## 子 agent 标准 prompt 契约

每个 subagent 必须只收到并只处理一个模板。prompt 必须包含：

- 模板全文，包括适用范围、前置声明、必须写什么、推荐结构。
- `README.md` 全局元规则。
- 原文路径、可用检索方式和输出路径。
- 覆盖模式：默认 overwrite；用户明确要求增量时使用 Mode merge。
- 硬约束：按推荐结构骨架输出；字段无依据写“原文未说明”或“待核验”；禁止为补齐字段编造；区分“原作事实 / 我的判断 / 待核验”；不粘贴大段原文，只给章节/行号和短摘要。

subagent 输出必须直接写入 plan 指定的输出路径。若发现模板与原文完全不匹配，也要写出一份说明文档，列出无法完成的字段和需要用户确认的问题。

## 覆盖与增量约束

默认 overwrite：可以重写目标文档，但仍必须遵循模板推荐结构和证据规则。

Mode merge：必须先读取旧文档，把它视为已有人工成果；保留高质量内容，只补缺、纠错、追加遗漏证据。发生大改写时，先在文档开头写“本次变更摘要”，并把旧文件保存为同目录 `.bak`，或移至文末“历史版本”小节。不得静默推倒已有人工文档。

若 Mode merge 时目标文档尚不存在，按首次生成处理，并在文档开头说明本次为首次生成，不需要 .bak。

## 质量基线

输出质量参考 `凡人修仙传/法宝妖兽丹药分析.md`：关注结构密度、体系分层、核心条目表、机制链和证据，而不是模板示例行里的占位内容。

所有结论必须能回溯到原文证据。没有来源的信息使用“原文未说明”或“待核验”，不要为了完整性虚构。

## Python 辅助边界

candidate/evidence 抽取仅为 entity_table 类模板寻找漏网名词和证据片段。叙事 / 关系 / 流程类模板，例如事件因果链、人物关系、修炼历程、职业闭环，可直接由 subagent 检索原文并撰写。

旧的 review-pack、review shard、finalize-reviewed 管线仍可作为单模板实体表工作流使用，但它不是批量文档生成主流程。

## Template-First Flow

当只处理单个模板时，先运行 `profile-template` 或 `prepare-framework`。如果模板画像 confidence 低于配置阈值，先向用户确认 shape、字段和禁止输出形式。

## Windows Runtime Rules

- Always set UTF-8 console and `PYTHONIOENCODING=utf-8` before invoking Python.
- Do not pipe PowerShell here-strings directly into `python -`; BOM bytes can break the first Python token.
- Put multi-line Python probes in a `.py` file or use an existing wrapper.
- Runtime extraction should not run pytest, plugin validation, cachebuster updates, or git commits.

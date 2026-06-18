# 优化方案 V2：LangExtract 零遗漏抽取 + 大模型成文

> 最后更新：2026-06-18
> 状态：方案定稿（待 Codex 执行）
> 取代：`docs/优化方案-模板驱动并行生成.md`（V1，方向有误，见 §1）
> 适用范围：`cultivation-worldbuilding-research` 插件

---

## 0. 目标（用户原话校准）

> 读取大的原文（《凡人修仙传》1500 万字），**不漏掉任何内容**。比如丹药分析，**不能漏掉任何丹药**。先通过 Python 脚本进行各种处理，**最后大模型完善**。

硬要求：**高召回 / 零遗漏**（一个丹药都不能漏）+ **可溯源**（每条能回到原文）+ **最终产出按模板撰写的成品文档**。

---

## 1. 为什么推翻 V1 与老正则管线

| 方案 | 致命缺陷 |
|---|---|
| **老正则管线**（`candidate_extractor.py`） | 抽取靠正则后缀匹配，不理解语义 → 30 万条噪声候选；规则外的（无后缀/作者造词）必漏；产不出成品文档。 |
| **V1（subagent 直读大原文）** | 让大模型直接 grep+分段读 1500 万字 → 触发 **Lost-in-the-Middle**（长上下文中间召回退化），**必漏**，违背零遗漏要求。 |

参考资料（`E:\AI_Projects\修仙游戏调研\docs\参考资料\信息抽取`）给出的正确范式（LangExtract / LLM-IE）共识：
**不要把整篇文档喂给 LLM（实验证明更差）；要切成小单元、逐块抽取、多趟提召回、对齐溯源、合并去重。**

LangExtract README 原文：
- "Optimized for Long Documents: Overcomes the needle-in-a-haystack challenge ... text chunking, parallel processing, and multiple passes for higher recall."
- "extraction_passes=3 improves recall through multiple passes; max_workers=20 parallel; max_char_buffer=1000 smaller contexts for better accuracy."

LLM-IE README 原文：
- "Instead of prompting LLMs with the entire document (worse performance), we divide the input into units (sentences/lines/paragraphs). LLM focuses on one unit at a time."

---

## 2. 目标架构

```
1. 切块            Python（LangExtract）：1500万字 → 小块（max_char_buffer）。不把整本喂模型。
2. 逐块抽取        MiniMax-M2.7（大模型）：每块按模板字段做结构化抽取。
   ├─ 多趟         extraction_passes=3：同块抽多遍，提高召回（防漏）。
   └─ 并行         max_workers：多块并发。
3. 对齐溯源        Python（LangExtract）：每条抽取定位回原文 char 区间（grounding）。
                  char_interval=None 的（模型编的、对不上原文的）过滤掉。
4. 合并去重        Python：跨块同一实体合并 → 全书丹药聚合成一张总表（带证据位置）。
5. 完善成文        MiniMax-M2.7（大模型）：基于已抽全的结构化结果 + 模板「推荐结构」，写成最终 .md。
6. 可视化(可选)    LangExtract：生成交互 HTML，人工抽查召回与溯源。
```

**分工铁律**：Python 只做不需要理解内容的机械活（切块、对齐、合并、去重、渲染脚手架）；**所有"理解/抽取/判断/撰写"由 MiniMax 大模型做**。这正是"先 Python 处理，最后大模型完善"，且抽取本身也是大模型（不是正则）。

---

## 3. 模型后端（已实测确认）

- **接口**：MiniMax OpenAI 兼容，`base_url = https://api.minimaxi.com/v1`（国内站；`.io` 国际站对此 key 返回 401，勿用），走 `/v1/chat/completions`。
- **抽取 & 成文模型**：`MiniMax-M2.7`（用户指定；实测可用，带 `<think>` 思维链）。
- **密钥**：已写入插件根 `.env` 的 `MINIMAX_API_KEY`，并已 `.gitignore`（`git check-ignore .env` 通过）。代码**只从环境/.env 读，禁止硬编码**。
- LangExtract 接法：
  ```python
  from langextract.factory import ModelConfig
  config = ModelConfig(
      model_id="MiniMax-M2.7",
      provider="openai",
      provider_kwargs={"api_key": os.environ["MINIMAX_API_KEY"],
                       "base_url": os.environ.get("MINIMAX_BASE_URL","https://api.minimaxi.com/v1")},
  )
  ```
- ⚠️ M2.7 是推理模型，每块都走思维链 → 海量块时速度/成本偏高。验证阶段须实测单模板的耗时与 token 花费，作为是否铺开 37 个的依据。

---

## 4. 验证范围（用户已定）

先跑 **3-5 个代表模板，覆盖不同形状**，验证零遗漏与成本：

| 模板 | 形状 | 验证点 |
|---|---|---|
| 丹药分析模板.md | entity_table | 实体穷举零遗漏（核心诉求） |
| 事件因果链（长程因果图）模板.md | process_chain | 流程/因果类抽取 |
| 人物关系与事件分析模板.md | relationship_chain | 关系类抽取 |
| 功法术法神通模板.md | cards_only | 卡片类 |
| 势力设定模板.md | overview_plus_cards | 总览+卡片 |

每个模板产出一篇成品 `<主题>.md` 写回原文目录，并保留中间产物（抽取 jsonl、可视化 html）供抽查。**先不铺 37 个**；这 5 个质量与成本满意后再扩。

---

## 5. 实施任务（交付 Codex，TDD）

> 沿用 V1 的工程纪律：每个改动先写失败测试→实现→测试转绿；Windows 下设 UTF-8；不擅自提交；模板/原文读用 `utf-8-sig`（真实模板带 BOM，原文是 gb18030——见 §7）。

### 5.0 实施前审查补充（2026-06-18）

为避免把 V2 做成只服务当前 5 个模板的一次性脚本，编码前按以下边界执行：

- **通用架构**：新增 LangExtract 管线不替换旧正则链条，而是作为独立入口接入现有 `template_profile.py`、`encoding.py`、`config_loader.py`。旧链条只标记为历史/粗筛路径，避免破坏既有测试。
- **设计模式适配**：MiniMax 接入采用 provider 工厂封装；LangExtract 调用、成文调用、可视化写入均通过可注入函数封装，单元测试使用 mock，不真实消耗 API。
- **配置化覆盖范围**：`model_id`、`base_url`、`extraction_passes`、`max_workers`、`max_char_buffer`、输出文件名、真实文档测试的 `limit_chars`/dry-run 行为、是否生成可视化、token 估算参数都必须来自配置或 CLI 参数，不写死在模板专属代码里。
- **模板泛化**：prompt 与 few-shot examples 必须从模板画像的字段表、推荐结构、README 元规则生成。丹药、功法、势力等名称只允许出现在测试 fixtures 或真实模板数据中，不进入通用逻辑分支。
- **真实文档测试护栏**：允许用真实《凡人修仙传》原文的显式 `limit_chars` 小样本做开发验证；任何截断、跳过、dry-run 都必须写入 run-summary，不能伪装成全书零遗漏验证。

### Task A：引入 LangExtract 依赖与 MiniMax provider
- 在插件加 `langextract`（`pip install langextract[openai]`）依赖说明（requirements 或 pyproject）。
- 新增 `scripts/pipeline/minimax_provider.py`：封装 `ModelConfig`，从 `.env`/环境读 key 与 base_url，暴露 `build_model_config(model_id="MiniMax-M2.7")`。
- 测试：mock 环境变量，断言 config 的 base_url/provider 正确；无 key 时报清晰错误。

### Task B：原文读取与切块（Python，零成本）
- 新增 `scripts/pipeline/extraction_runner.py`：
  - 读原文（`utf-8-sig` 失败回退 `gb18030`，见 §7），
  - 调 LangExtract `lx.extract(..., extraction_passes=3, max_workers=可配, max_char_buffer=可配)`，
  - 抽取 prompt 与 few-shot examples **从模板的「必须写什么」字段表 + 「推荐结构」自动生成**（复用 `template_profile.py`），不硬编码某模板。
- 配置项（放 YAML，非硬编码）：`extraction_passes`、`max_workers`、`max_char_buffer`、`model_id`。
- 测试：用一小段假原文 + mock 模型，断言切块数、passes 生效、char_interval 过滤逻辑。

### Task C：few-shot examples 生成器
- 从模板「推荐结构」里的示例行（如丹药模板那张含"聚气丹/筑基丹"的表）转成 LangExtract `ExampleData`（verbatim、按出现顺序）。
- 这是召回质量关键：examples 驱动模型行为。
- 测试：给定丹药模板，断言生成的 examples 含正确 extraction_class 与字段。

### Task D：合并去重 + 成文
- 合并：跨块同名实体聚合，保留所有证据 char 区间。
- 成文：把聚合后的结构化结果 + 模板「推荐结构」骨架 + README 元规则，交 MiniMax-M2.7 写成最终 .md（区分原作事实/我的判断/待核验；无依据写"原文未说明"）。
- 测试：mock 抽取结果，断言合并去重正确、成文调用拿到完整结构化输入。

### Task E：批量入口 + 验证脚本
- `scripts/run_extraction.ps1`：入参 `-Template/-TemplateDir -SourceFile -OutputDir -Model -Passes -Workers -MaxCharBuffer`。
- 先支持单模板与"指定 N 个模板"两种；输出成品 .md + 中间 jsonl + 可视化 html + 一份 run-summary（块数、抽取条数、去重后条数、耗时、token 估算）。
- 测试：参数契约、UTF-8/中文路径、单模板冒烟（可对超小假原文）。

### Task F：废弃标记
- 老正则管线（candidate_extractor 链）与 V1 的 batch_plan/subagent 路径：在 SKILL.md 标注"已被 V2 LangExtract 流程取代，仅作历史/辅助粗筛"。不删代码，避免连带破坏测试。

---

## 6. 成本与召回护栏（必须做）
- **先单模板（丹药）实跑**，打印：总块数、调用次数、耗时、token 消耗、抽到的丹药去重后数量。用户看完估算全量成本再决定铺开。
- **召回自检**：用 LangExtract 可视化 html 人工抽查；并可跑第二趟不同 `max_char_buffer` 对比新增条目，量化"还在漏多少"。
- **不静默截断**：任何采样/上限/跳过都要 log 出来。

---

## 7. Windows / 编码硬约束（实测踩坑）
- 真实模板：UTF-8 **带 BOM** → 读模板用 `utf-8-sig`。
- 原文 `凡人修仙传.txt`：实测编码 **gb18030**（老管线 inspect 报告确认）→ 读原文须 `gb18030`（或用现有 `encoding.py` 的回退链）。
- PowerShell 5.1：先设 `PYTHONIOENCODING=utf-8` + `[Console]::OutputEncoding=UTF8` + `chcp 65001`；读 JSON 用 `Get-Content -Encoding UTF8`。
- `.env` 已 gitignore；密钥只从环境读。

---

## 8. 验收标准
1. 给定一个模板 + 原文，产出一篇符合该模板「推荐结构」的成品 .md，写回输出目录。
2. 丹药模板：抽取的丹药为**全书去重总表**，每条带原文证据位置；人工抽查无明显遗漏（对比可视化）。
3. 抽取由 MiniMax-M2.7 逐块完成（多趟+并行），Python 不做内容判断。
4. 成品区分原作事实/我的判断/待核验，无编造。
5. run-summary 给出块数/调用数/耗时/token，可据此估全量成本。
6. 5 个代表模板各跑通；`pytest` 绿。

---

## 9. 待用户后续确认
- M2.7 海量抽取成本若过高，是否允许抽取换更便宜型号、仅成文用 M2.7（代码已做成可配置）。
- 验证通过后再决定铺开到 37 个模板。
- **安全**：当前 key 已出现在对话记录，建议验证后在 MiniMax 控制台轮换密钥。

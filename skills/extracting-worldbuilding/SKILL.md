---
name: extracting-worldbuilding
description: Use when extracting worldbuilding research from long fiction or game text with configurable templates, evidence packs, and Markdown report validation.
---

# Extracting Worldbuilding

Run the shared pipeline before drafting conclusions.

1. Identify source text, template, and work directory.
2. Prefer `scripts/run_worldbuilding_pipeline.ps1` for Windows runs so UTF-8, paths, and command order stay consistent.
3. If running manually with a template, run `profile-template` or `prepare-framework` before extraction.
4. Keep final report aligned to the selected template.
5. Do not treat candidates as confirmed facts until they have source spans and review status.
6. Keep domain rules in YAML; do not hardcode names from a specific novel in Python.

## Template-First Flow

When a template is available, start by profiling it with `profile-template` or generating a run-local framework with `prepare-framework`.

- If the template profile reports `low confidence` or confidence below `0.6`, present its `questions` and ask the user before running extraction.
- Use generated `route.json`, `rule-pack.yaml`, and `curation.yaml`; they must be reused by extract-candidates, make-review-pack, finalize-reviewed, and render.
- Keep `route.json` as the rendering and validation contract for the run instead of falling back to registry defaults once a local route exists.

## No-Template Flow

When the user has no template, run `suggest-analysis-points` from the closest available source template or requested subject type.

- Ask the user to confirm fields, report shape, and forbidden output modes before creating a run-local template.
- Create run-local template and framework files only after confirmation.
- Do not infer a final schema from a single extraction result.

## Multi Agent Shard Contract

Python scripts prepare review work; they do not spawn Codex agents.

- Input shard source: `review-pack.jsonl`.
- Reviewer shard output: `review-decisions.parts/part-{index}.jsonl`.
- Each JSONL line contains `review_id`, `decision`, `name`, `fields`, `source_span_ids`, and `notes`.
- Main workflow collects shard decisions before merge, validation, render, and final review.

## Final Review Loop

Review only after a draft report exists.

Loop until accepted: review -> revise route/rules/curation/decisions -> re-render -> re-review -> confirm.

## Windows Runtime Rules

- Always set UTF-8 console and `PYTHONIOENCODING=utf-8` before invoking Python.
- Do not pipe PowerShell here-strings directly into `python -`; BOM bytes can break the first Python token.
- Put multi-line Python probes in a `.py` file or use a known wrapper that strips a leading BOM.
- Runtime extraction should not run pytest, plugin validation, cachebuster updates, or git commits.

## Wrapper Script

Use the plugin wrapper for normal extraction runs:

```powershell
& 'C:\Users\Administrator\plugins\cultivation-worldbuilding-research\scripts\run_worldbuilding_pipeline.ps1' `
  -Source '<source.txt>' `
  -Template '<template.md>' `
  -Workdir '<run-dir>' `
  -Request '<user request>'
```

Add `-Confirmed <confirmed.json>` to render a Markdown report, and add `-Expected <expected.yaml>` to run validation.

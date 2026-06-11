---
name: extracting-worldbuilding
description: Use when extracting worldbuilding research from long fiction or game text with configurable templates, evidence packs, and Markdown report validation.
---

# Extracting Worldbuilding

Run the shared pipeline before drafting conclusions.

1. Identify source text, template, and work directory.
2. Prefer `scripts/run_worldbuilding_pipeline.ps1` for Windows runs so UTF-8, paths, and command order stay consistent.
3. If running manually, run `inspect`, `segment`, `route-template`, `extract-candidates`, `build-evidence`, `render`, and `validate` in that order.
4. Keep final report aligned to the selected template.
5. Do not treat candidates as confirmed facts until they have source spans and review status.
6. Keep domain rules in YAML; do not hardcode names from a specific novel in Python.

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

---
name: extracting-worldbuilding
description: Use when extracting worldbuilding research from long fiction or game text with configurable templates, evidence packs, and Markdown report validation.
---

# Extracting Worldbuilding

Run the shared pipeline before drafting conclusions.

1. Identify source text, template, and work directory.
2. Run `inspect`, `segment`, `route-template`, `extract-candidates`, `build-evidence`, `render`, and `validate`.
3. Keep final report aligned to the selected template.
4. Do not treat candidates as confirmed facts until they have source spans and review status.
5. Keep domain rules in YAML; do not hardcode names from a specific novel in Python.

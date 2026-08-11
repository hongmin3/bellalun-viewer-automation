# Repository working rules

These instructions apply to the entire repository.

## Required workflow

1. Read `README.md`, `NEXT_TASK.md`, the user-attached checklist, and the relevant manuals/specifications before changing automation behavior.
2. Do not guess when a Bellalun UI action, expected result, or destructive behavior is unclear. Inspect read-only evidence first and ask the user when the answer cannot be established safely.
3. Implement UI automation as standalone Python code that runs without an AI session and emits PASS/FAIL evidence.
4. Prefer Win32 control IDs, visible text, OCR, and window-relative geometry. Never use absolute desktop coordinates when a portable selector is possible.
5. Run proportionate validation after every automation change. At minimum run Python compilation; run the affected live TC when the required external systems are available.
6. After completing an automation request, inspect the diff, stage only relevant source/documentation changes, commit them, and push them to the GitHub remote in the same task.
7. Never commit `config.json`, credentials, tokens, patient/runtime data, DICOM files, or generated `Reports/`, `Evidence/`, `Log/`, `Cache/`, and `Temp/` contents.
8. Do not rewrite published history or force-push. If commit or push fails, report the exact blocker rather than claiming completion.

## Git conventions

- Remote: `https://github.com/hongmin3/bellalun-viewer-automation.git`
- Default branch: `main`
- Use a concise commit message describing the TC or automation change.
- Report the pushed branch and commit SHA in the final response.


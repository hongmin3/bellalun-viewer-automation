# Repository working rules

These instructions apply to the entire repository.

## Required workflow

1. Read `README.md`, `NEXT_TASK.md`, the user-attached checklist, and the relevant manuals/specifications before changing automation behavior. Also read the durable guidance in `..\지식\`: `[자동화 구현 현황] Bellalun Viewer auto 구현 상태.md` (what's implemented, wired into `run.py`, and last verified — read this first for a quick status pass), `[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md` (implementation rules: state-based waiting, log-timestamp filtering, PASS/FAIL evidence policy, GPU-less handling, fixture freshness, session-separation), and `[QA 작성 규칙] Bellalun Viewer TC 설계·자동화·자체검토 가이드.md` (TC design methodology). Update the 구현 현황 doc when you change what's implemented or wired up. `HANDOFF.md`, when present, is a one-off per-session handoff only — durable rules live in the `지식` folder, not there.
2. Do not guess when a Bellalun UI action, expected result, or destructive behavior is unclear. Inspect read-only evidence first and ask the user when the answer cannot be established safely.
3. Implement UI automation as standalone Python code that runs without an AI session and emits PASS/FAIL evidence.
4. Prefer Win32 control IDs, visible text, OCR, and window-relative geometry. Never use absolute desktop coordinates when a portable selector is possible.
5. Every check (current or new TC) must record what was actually compared — expected/actual values, and a note naming the log/DB/file/UI-reread evidence used — so a PASS/FAIL verdict is auditable from the report alone. Never confirm success from a log phrase alone; corroborate with DB/file/UI state where possible. See `지식` guidance for the log-timestamp-filtering requirement on log-based waits.
6. For GPU/Reconstruction-dependent TCs, a confirmed no-GPU error (e.g. exact `No GPUS`) only excuses the result-generation assertion (SKIP it) — never a behavioral assertion that must hold regardless of GPU (e.g. parameter retention after Apply). Determine GPU availability from the step that actually attempts and logs it, not a later step that may not re-attempt.
7. Run proportionate validation after every automation change. At minimum run Python compilation; run the affected live TC when the required external systems are available.
8. After completing an automation request, inspect the diff, stage only relevant source/documentation changes, commit them, and push them to the GitHub remote in the same task.
9. Never commit `config.json`, credentials, tokens, patient/runtime data, DICOM files, or generated `Reports/`, `Evidence/`, `Log/`, `Cache/`, and `Temp/` contents.
10. Do not rewrite published history or force-push. If commit or push fails, report the exact blocker rather than claiming completion.

## Git conventions

- Remote: `https://github.com/hongmin3/bellalun-viewer-automation.git`
- Default branch: `main`
- Use a concise commit message describing the TC or automation change.
- Report the pushed branch and commit SHA in the final response.


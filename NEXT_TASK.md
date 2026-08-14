# Next automation handoff

## Next priority

Implement `TC_Basic_WorkFlow_04` as far as the attached checklist, manuals, and available test environment safely allow. Start by reading its exact TC row and Expected Result; do not infer steps from the ID alone.

## Current verified state

- Repository: `hongmin3/bellalun-viewer-automation`
- Local working directory: `C:\Users\2024980\Documents\자동화\Bellalun Viewer\auto`
- Knowledge/manual directory: `C:\Users\2024980\Documents\자동화\Bellalun Viewer\지식`
- `TC_Basic_WorkFlow_01` is implemented by `tests/workflow01.py` and passed all nine MWL + Local steps in a live run.
- `TC_Basic_WorkFlow_02` is implemented by `tests/workflow02.py` and passed a live Viewer run on 2026-08-11. `python run.py run-wf02` reopens the latest empty suspended `DATA_FLOW_MWL_01`, registers LCC 2D/LCC 3D-N, performs gated Demo F8 acquisition, validates one each of InstanceType 0/1/2/3, applies W/L, Zoom, Pan, and Arrow Annotation to 2D and 3D Recon with OCR/screenshot-delta evidence, closes the exam, and verifies it again in Examined.
- `TC_Basic_WorkFlow_03` is implemented by `tests/workflow03.py` and passed the final live regression on 2026-08-11. It creates/reuses `TC_WF03_OVERLAY` only under Setting > DICOM > Print Overlay, registers Patient ID/Birth Date/Thickness/Compression Force/HVL/AGD, applies it to `PRINT_TEST`, switches Film from 2x2 to 1x1, performs actual DICOM Print, and compares the Film values/raster with the new Print server web preview. Final job 41 passed all six OCR values with image similarity 0.989924.
- Initial-state regression is available as `python run.py run-regression`. Performance optimization (state-based waits replacing fixed sleeps) is complete and re-verified live on 2026-08-14: report `Result_20260814_095214` took ~895s end-to-end vs the 2026-08-11 pre-optimization baseline of 1290.6s (~30.7% faster). DICOM, WF01, WF02, WF03, XIPL_01, and XIPL_02 passed their data-backed checks. XIPL_03 correctly failed because all ten values reverted to defaults after Apply/reopen; exact `No GPUS` exempted only result generation as SKIP.
- `TC_XIPL_compatibility_03` always reopens Post Reconstruction after Apply and rereads all ten values. Parameter name/value retention is mandatory even without a GPU, so default-value reversion is FAIL. Exact `No GPUS` exempts only Recon/Synthetic output creation as SKIP (GPU availability is judged from Preview's log, since Apply does not re-attempt/re-log initialization). Any other Recon error remains FAIL; on a GPU machine DB/file output delta is also mandatory.
- Fixed 2026-08-14: `_post_recon_complete()`'s Apply-completion check now filters log lines by their own embedded timestamp (`_log_lines_from`), not just byte-offset marks — a buffered log flush could otherwise leak Preview's own delayed thread-exit line into Apply's completion check and falsely pass Apply in <1s.
- Fixed 2026-08-14: `tests/xipl_flows.py::_prepare()` now checks `vp.fixture_is_fresh(ctx, patient_id)` before reusing the `DATA_FLOW_MWL_01` fixture; if no same-day InstanceType 0/1/2/3 study exists (e.g. running `run-xipl-01/02/03` standalone days after WF01/WF02 last ran), it automatically reruns WF01 then WF02 to regenerate today's fixture first. `run-regression` is unaffected since WF01/WF02 already ran.
- Durable operational rules (state-based waiting, log-timestamp filtering, PASS/FAIL evidence policy, GPU-less handling, fixture freshness, session separation) now live in `..\지식\[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md`, not in a one-off handoff file — read it before changing automation behavior.
- Install_01 is MANUAL until `config.json > release_note` is replaced with an approved Release Note; the current `_source` explicitly says the captured baseline must be replaced. Installed Bellalun/DB version observed in regression was 1.0.12.105.
- DICOM setup is implemented by `core/dicom_settings.py`.
- Verified servers:
  - MWL: `MWL_TEST / MWL_SCP / 10.13.0.222:11112`
  - Storage: `BUNNY_TEST / Bunny / 10.201.0.139:3000`, the only `Use=1` Storage entry
  - Print: `PRINT_TEST / PRINT_SCP / 10.13.0.222:11113`
- Storage setup checks Burn Annotation/Label/Information, Apply preview position, and sets Dose SR to Send.
- Every Echo must have the successful association sequence and no `Connected Fail` result.
- Print server web endpoint verified: `http://10.13.0.222:8000/viewer.html?id=<job>` displays the same `/api/jobs/<job>/preview` image used by the independent Python assertion.

## Useful commands

```powershell
python run.py setup-dicom
python run.py setup-storage
python run.py run-wf01
python run.py run-wf02
python run.py run-wf03
python run.py portability-check
```

The real `config.json` and generated evidence/reports are intentionally local and ignored by Git. Preserve them; use `config.example.json` only as the repository template.

## Completion rule

When `TC_Basic_WorkFlow_04` work is complete, update this file to the next TC or remove it, then follow `AGENTS.md`: validate, commit, and push all relevant automation source changes without committing local configuration or runtime evidence.

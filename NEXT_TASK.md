# Next automation handoff

## Next priority

Implement `TC_Basic_WorkFlow_03` as far as the attached checklist, manuals, and available test environment safely allow. Start by reading the exact TC row and expected results from the checklist the user attaches in the new conversation. Do not infer the TC steps from its ID alone.

## Current verified state

- Repository: `hongmin3/bellalun-viewer-automation`
- Local working directory: `C:\Users\2024980\Documents\자동화\Bellalun Viewer\auto`
- Knowledge/manual directory: `C:\Users\2024980\Documents\자동화\Bellalun Viewer\지식`
- `TC_Basic_WorkFlow_01` is implemented by `tests/workflow01.py` and passed all nine MWL + Local steps in a live run.
- `TC_Basic_WorkFlow_02` is implemented by `tests/workflow02.py` and passed a live Viewer run on 2026-08-11. `python run.py run-wf02` reopens the latest empty suspended `DATA_FLOW_MWL_01`, registers LCC 2D/LCC 3D-N, performs gated Demo F8 acquisition, validates one each of InstanceType 0/1/2/3, applies W/L, Zoom, Pan, and Arrow Annotation to 2D and 3D Recon with OCR/screenshot-delta evidence, closes the exam, and verifies it again in Examined.
- DICOM setup is implemented by `core/dicom_settings.py`.
- Verified servers:
  - MWL: `MWL_TEST / MWL_SCP / 10.13.0.222:11112`
  - Storage: `BUNNY_TEST / Bunny / 10.201.0.139:3000`, the only `Use=1` Storage entry
  - Print: `PRINT_TEST / PRINT_SCP / 10.13.0.222:11113`
- Storage setup checks Burn Annotation/Label/Information, Apply preview position, and sets Dose SR to Send.
- Every Echo must have the successful association sequence and no `Connected Fail` result.
- Print Overlay is intentionally deferred to a separate automation request.

## Useful commands

```powershell
python run.py setup-dicom
python run.py setup-storage
python run.py run-wf01
python run.py run-wf02
python run.py portability-check
```

The real `config.json` and generated evidence/reports are intentionally local and ignored by Git. Preserve them; use `config.example.json` only as the repository template.

## Completion rule

When `TC_Basic_WorkFlow_03` work is complete, update this file to the next TC or remove it, then follow `AGENTS.md`: validate, commit, and push all relevant automation source changes without committing local configuration or runtime evidence.

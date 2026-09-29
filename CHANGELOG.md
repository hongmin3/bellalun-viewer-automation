# Changelog

현재 사양은 [SPEC.md](SPEC.md), 진행 상태와 과거 검증 근거는 [progress.md](progress.md)에 둔다.

## 2026-09-29

### Changed

- 공통 SPEC workflow를 v7로 올렸다(키트 관리 블록과 `.project-check/` 검사기·렌더러 교체). 이 프로젝트는 단일 파일 `SPEC.md`를 그대로 쓴다. 제품 동작은 바뀌지 않았다.
- 프로젝트 폴더가 `C:\자동화\Bellalun Viewer` → `C:\자동화\projects\Bellalun Viewer`로 옮겨졌다. 저장소 안 경로는 모두 상대 경로라 코드는 바뀌지 않았다.

## 2026-09-22

### Changed

- 자동화 Workspace의 SPEC/readiness workflow를 도입하고 현재 요구사항과 구현·테스트 연결을 문서화했다.
- 기존 진행 문서의 고유 운영 사실과 미완료 제품 작업을 보존했다.
- 이번 변경은 governance-only(관리 체계 도입)이며 기존 런타임 동작을 유지한다.
  제품 기능을 추가하거나 변경하지 않았으며 새 제품 검증·배포 완료를 의미하지 않는다.

# Changelog

현재 사양은 [SPEC.md](SPEC.md), 진행 상태와 과거 검증 근거는 [progress.md](progress.md)에 둔다.

## 2026-10-15

### Added

- REQ-DIST-001, REQ-DIST-002: BellalunAuto의 한국어 실행·설정 화면, 작업 폴더 분리, 읽기 전용 자체진단, 기존 CLI 연결을 구현했다. 자기 EXE의 worker 감시, PC 공통 제품 잠금, UAC 경로 전달, 중지·비정상 종료 정리와 비공개 로그 처리를 포함한다.
- REQ-DIST-003: 승인 자료 manifest·해시 검사, Nuitka standalone·Inno Setup 빌드, 포터블 ZIP과 빌드 정보 생성을 구현했다. 사내 원문·Baseline·설치 산출물은 공개 배포 대상에서 제외한다.
- REQ-WU-001: USB Import 완료 메시지, 환자 범위 전후 DB UID, 실제 영상 파일과 Examined 클릭 로그를 연결하는 판정을 구현했다. 단독 실측에서 Imported 1 / Skipped 0, 신규 검사 1건·영상 3건, 파일 XML UID와 재검색 결과의 일치를 확인했다. 연결된 전체 흐름과 최종 설치판 검증은 별도로 수행한다.

### Fixed

- REQ-DIST-001, REQ-DIST-004: 선택한 OCR 실행 경로를 공통 OCR 호출에 연결하고 XIPL 기동 준비 대기를 보강했다. 설치 자료·승인 Baseline을 출력으로 덮어쓰지 않도록 경로·링크 검사를 추가하고, 명시한 승인 자료 경로를 보존한다.
- REQ-REGRESSION-001: DB가 미등록 상태일 때 Baseline 복원의 물리 파일명을 제품 표준 `{DB}.mdf` / `{DB}.ldf`로 지정한다. 기존 등록 경로는 유지한다. WF14의 DB 전수 대조는 중단 전에 전후 스냅샷과 전체 필드 차이를 남긴다.
- REQ-DIST-002, REQ-WU-001: 과거 회귀 변환과 실시간 실행을 구분하고, 새 live 전체 완료 메타데이터 없이 완료로 판단하지 않는다. USB 부재·실패·미완료와 설정 순회 실패의 판정도 보존한다.
- REQ-WU-001: Export 성공 문구·증거·단일 버튼을 확인하고 프로세스 종료를 별도 대기한다. 실제 Export OK ID 800을 확인했으며 부분 Import는 영상 수 비교로 거절한다. 늦게 뜨는 중복 환자 팝업도 제한 시간 안에서 처리한다.
- REQ-DIST-003: Inno Setup 6.7.3에서 사용할 수 없는 PATH 분할 함수를 명시적 토큰 분할로 교체하고 실제 설치 스크립트 컴파일 회귀 검사를 추가했다.
- REQ-DIST-002: Nuitka standalone에서 `sys.executable`이 존재하지 않는 `python.exe`를 반환하는 경우를 재현했다. Windows 실제 EXE 경로로 자식 작업을 실행하며 소스 실행과 명시한 실행 경로는 유지한다.

### Validation

- REQ-DIST-004, REQ-WU-001: 단위시험 392개와 하위 사례 202개가 통과했다. 변경 전 소스 전체 회귀는 TC 27건 중 PASS 17 / FAIL 8 / MANUAL 2였으며 수정 후 전체 결과를 대신하지 않는다.
- REQ-REGRESSION-001: WF14 단독 재시험에서 DB 38개 영역, 전후 56개 페이지와 목록 89행·849항목 복원을 확인했다. 기존 UPS 미복원만 FAIL이며 원복 정리는 PASS다. 기존 WU11 기준에 따른 조회 전용 매핑은 PASS이며 실제 live 전체를 대체하지 않는다.
- REQ-DIST-004: 한글·공백이 있는 다른 드라이브에서 후보2 설치·업데이트·재설치·제거 보존과 새 셸 검증을 통과했다. 최초 GUI 설정 저장과 설치판 자체진단 20항목도 통과했다. 자식 실행 경로 수정 후 새 최종 빌드로 재확인한다. 동일 최종 EXE의 두 전체 실행과 개발 도구 없는 PC 검증은 미완료다.

## 2026-09-29

### Changed

- 공통 SPEC workflow를 v8로 올리고 `SPEC.md` 1절에 프로젝트 전체 흐름을 보여 주는 "한눈에 보기" 흐름도를 더했다. `docs/SPEC.html` 1절에 그림으로 보인다. 제품 동작은 바뀌지 않았다.
- 공통 SPEC workflow를 v7로 올렸다(키트 관리 블록과 `.project-check/` 검사기·렌더러 교체). 이 프로젝트는 단일 파일 `SPEC.md`를 그대로 쓴다. 제품 동작은 바뀌지 않았다.
- 프로젝트 폴더가 `C:\자동화\Bellalun Viewer` → `C:\자동화\projects\Bellalun Viewer`로 옮겨졌다. 저장소 안 경로는 모두 상대 경로라 코드는 바뀌지 않았다.

## 2026-09-22

### Changed

- 자동화 Workspace의 SPEC/readiness workflow를 도입하고 현재 요구사항과 구현·테스트 연결을 문서화했다.
- 기존 진행 문서의 고유 운영 사실과 미완료 제품 작업을 보존했다.
- 이번 변경은 governance-only(관리 체계 도입)이며 기존 런타임 동작을 유지한다.
  제품 기능을 추가하거나 변경하지 않았으며 새 제품 검증·배포 완료를 의미하지 않는다.

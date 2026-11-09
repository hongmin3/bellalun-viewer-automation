# OCR 이식성 고도화와 1.0.3 릴리즈 계획

사용자가 앞서 제시한 개선 전부의 구현과 릴리즈 ZIP 제작을 요청했다.
사양: SPEC.md REQ-OCR-001, REQ-DIST-005/007, REQ-REGRESSION-002.
기존 uitext의 전처리·print_overlay의 DB 확인·Setup 빌더를 확장한다.
별도 OCR 엔진 교체나 DB를 통한 UI 대체는 하지 않는다.

- [ ] 공통 선택 판독: core/ocr_selection.py; 실패 시험 후 한 캡처·4가지 판독·유일 후보·신뢰도·점수차·실패 증거를 구현한다.
- [ ] 프린트 연결: core/print_overlay.py, core/uitext.py, tests/workflow03.py; 카탈로그/콤보/이름 선택을 공통화하고 DB/필름 판정을 보존한다.
- [ ] OCR 지문: core/ocr_runtime.py, bellalunauto/prerequisites.py; SHA-256·버전·eng 파일을 기록하고 기존 설정을 보존한다. 독립 담당자에게 이 범위만 위임한다.
- [ ] 저장 이미지 재판독: tools/ocr_replay.py와 시험; manifest 단위 결과와 실패 원인을 출력한다.
- [ ] 포장: Setup을 담는 배포 ZIP과 내부 체크섬·후보 표시·사용 안내를 만들며 ZIP 자체 CRC와 모든 내부 파일 SHA-256을 다시 확인한다. 포터블 실행판은 생성하지 않는다.
- [ ] 전체 단위시험·정적 검사·readiness·cleanup·검토 후 소스 커밋, 생략 없는 1.0.3 빌드, EXE 읽기 전용 smoke, ZIP 검증, 원격 push.

기준: 원격 main=d9cd99e, 설치판=5004de0/1.0.2. 저장소가 설치판보다 보고서 개선만 앞서 있다.
별도 worktree에서 작업하여 원래 체크아웃의 AGENTS.md 변경을 보존한다. 승인 사내 자료와 빌드 환경은 기존 위치를 절대경로로 참조하고 공개 Git에는 넣지 않는다.
재현 한계: 문제 PC의 당시 실패 크롭이 특정되지 않았다. 합성/저장 캡처와 단위시험을 제품 UI 성공으로 주장하지 않는다.
UI 회귀는 빌드 후 같은 EXE의 기본기능+WU 범위, 점유와 DB 복원·USB를 제시하고 별도로 승인받는다. 미수행이면 candidate ZIP으로 전달한다.

# TC 고도화 구현 계획

**목표:** REQ-TCUP-001~004에 따라 SKIP 기록·전체 목록·Overlay OCR·WU USB 준비 확인을 보강한다.
**실행:** 사용자가 구현·실패 시험·실물 단독 실행까지 지시한 범위를 이 세션에서 순서대로 수행한다.
**기술:** 기존 Python/unittest/pytest, Tkinter, Win32/OCR를 확장한다.
**사양:** `SPEC.md` REQ-TCUP-001~004, REQ-WU-003·004, REQ-VERDICT-002.

## 제약과 재사용 근거

- `core/setting_lists.py`의 문구·겹침·DB 수 증명을 유지한다. 현재 위치에서 아래로만 걷는 경로를 보강한다.
- `core/image_overlay.py`의 원본 크롭과 `core/uitext.py`의 다중 전처리를 재사용한다.
- `bellalunauto/runplan.py`, `qa_dialogs.py`, `gui.py`의 동의·실행 기록을 확장한다.
- VXvue `core/run_matrix.py`의 확인 목록/차단 분리와 `packaging/launcher.py`의 비대화형 명시 확인을 참고한다.
- Install_01·07~09와 발표자료는 등록만 한다. 저장점 재시도는 이후 실제 GUI 차단 수정으로 승격했다. 제품 판정 기준·기존 결과·녹화 원본은 보존한다.
- 최초 소스 실물 범위는 WF14·WF15·WU11·WU09였다. 이후 아래 추가 승인으로 실제 GUI 기본기능·WU 전체를 수행했다. 빌드·배포·설치는 제외한다.
- 최종 정리 → 자체 시험/정적 검사/readiness/workspace → 관련 문서 갱신 → 일반 commit/push.

## 공유 계약

`preparation_items(action)`는 `[{key, label}]`를 반환한다. `preparation_complete(action, checked)`는
필수 key 모두가 있는지 판정한다. GUI와 CLI가 같은 목록을 사용한다.
목록 수집 반환 형식과 OCR `dict[str,str]`, 기존 TCResult 형식은 유지한다.

## 검토 초점

중간 스크롤 위치, 가상 행 ID 재사용, OCR 미판독, USB 없음/확인 취소, 변환 경로의 무조작을 확인한다.

## 작업

- [x] 1. SKIP: 지정 목록과 회귀 결과의 TC·사유·판정을 검사하는 실패 시험 → scope 등급과 회귀 결과 보완 → 관련 시험.
- [x] 2. WF14: 중간 위치·재사용 ID·빈 목록·겹침 없음 시험 → 처음 이동과 안정된 끝 수집 → 목록 시험. WU11 매핑 확인.
- [x] 3. WF15: 기존 크롭 밖 문구가 추가 영역에서 읽히는 시험 → 줄 단위 OCR 보강 → Overlay 시험. 기대값 불변 확인.
- [x] 4. WU09: 미확인·USB 없음 차단 및 일반 회귀의 USB 불필요 시험 → GUI/CLI 체크리스트와 USB 단독 명령 → 관련 시험.
- [x] 5. 전체 단위시험·정적 검사·실물·복원 결과 문서 → 최종 정리·게이트·독립 검토.

## 2026-11-13 사용자 추가 승인

- 실행 중인 개별 시험과 복원을 먼저 마치고, 자동화 문제를 고친다.
- 최신 소스의 실제 BellalunAuto GUI에서 기본기능·실시간 Windows Update 전체를 각각 시작한다.
  GUI 버튼과 준비 확인창을 통과한 실행 기록·화면·리포트를 함께 확인하며 CLI 전용 실행을 GUI 증거로 대체하지 않는다.
- 앞선 빌드·재설치 제외 범위는 유지한다. 기존 설치판 1.0.11의 해시 정상과 소스 commit 조상 관계를 조회했다.
- 전체 결과와 복원을 확인한 뒤 문서·등급·검증·커밋·push까지 마친다. 실제 제품 결함과 SKIP은 성공으로 바꾸지 않는다.

## 완료 근거

기본기능 99.0분, 최종 WU 75.7분(PASS 10 / SKIP 3), 전수 목록·Overlay·USB와 복원 대조를 확인했다. 초기 실패와 복원 제한은 [실행 기록](../../tc-upgrade-2026-11-12.md)에 보존한다. 설치판·녹화 원본·기존 제품 FAIL은 유지했다.

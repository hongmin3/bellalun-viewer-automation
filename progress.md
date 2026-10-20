# 진행 상태

## 2026-10-20 최소 환경 실행 중 PC 꺼짐 원인 확인과 수정

다른 PC·Windows 11 LTSC 호환성 점검은 [호환성 검증 기록](docs/compatibility-2026-10-18.md)에 있다.

- 10/18 13:54 후보9 `--clean-env` 전체 실행은 약 1분 만에 PC가 꺼져 끝나지 않았다. 실행 기록 폴더는 그때 연결된
  USB(D:)에 있었고 10/20에는 USB가 분리되어 있었다.
- 원인: 최소 환경에서 `XIPL_PATH`가 빠져 Viewer가 E2100 뒤 PC 전원을 껐다(Viewer 로그, System 이벤트 1074).
- 수정: `core/product_env.py`. Viewer·XIPL Studio 실행 환경에 빠진 등록 환경 변수를 보충하고, `XIPL_PATH`가 맞지
  않으면 Viewer를 띄우지 않는다. 자체진단에 같은 항목을 더했다. 단위 401개 OK(skip 2).
- 후보10 정식 빌드: 소스 `20bf2f7`(dirty=false), EXE SHA256 `7bd7a362…53ed5`, setup SHA256 `a6e70206…d373`.
  빌드 내 테스트 463개 통과, 산출물 감사 12/12, PE 의존성 미해결 0. 같은 AppId 업데이트 설치 후 EXE 해시 일치.
- 후보10 경계 시험(`work/edge_cases.py`) ALL OK: 최소 환경·특수문자 경로·포터블 자체진단 22/22(새 XIPL 항목 포함),
  잘못된 설정 3항목만 FAIL, 긴 작업 폴더 1항목만 FAIL, 일반 사용자 권한은 관리자 권한 1항목만 FAIL.
  E5는 `cmd /c`가 경로 속 `%TEMP%`를 펼쳐 엉뚱한 폴더를 보던 시험 스크립트 문제를 고쳐 다시 수행했다.
- 2026-10-20 17:28 후보10 최소 환경 전체 실행(기본 → 실시간 WU)을 시작했다. 같은 최소 환경에서 Viewer가
  17:36 E2100 없이 초기화했고 전원 끄기 이벤트는 없었다. 기록 폴더 `C:\BellalunAuto 실행 기록\후보10-cleanenv-20261020_172820`(Git 제외).
  USB가 분리된 상태라 WU_09는 USB 부재로 기록될 수 있다.
- 후보10 최소 환경 기본기능 전체(17:28~19:16): 27 TC PASS 23 / FAIL 2 / MANUAL 2.
  XIPL03은 기존 제품 결함과 같다. WF14는 제품 결함이 아니었다. 작업 폴더 경로의 `%TEMP%`를 Windows 저장
  대화상자가 환경 변수로 바꿔 읽어 Export 파일 이름을 거부했다(`Evidence/Flow/14_Setting/99_error.png`).
- 수정: 작업 폴더 경로에 `%`가 있으면 제품 조작 실행을 시작 전에 거부하고 자체진단에 "작업 폴더 경로 문자"를 더했다.
  단위 403개 OK(skip 2). 같은 작업 폴더의 실시간 WU 전체(19:16 시작)는 비교용으로 끝까지 둔다.
- 후보10 최소 환경 실시간 WU 전체(19:16~20:20): live, chain_completed=true. 13 TC PASS 7 / FAIL 3 / MANUAL 3.
  - WU_09: WF09 Export 뒤 Export Manager가 20초를 넘겨 열려 FAIL(USB 단계는 USB 분리로 수행하지 않음).
  - WU_10·WU_11: 늦게 열린 Export Manager가 남아 최전면을 쥐어 Viewer 로그인 3회 실패. WU_11은 `%` 경로 문제도 겹친다.
  - 수정: Export Manager 대기 60초, Viewer 재기동 전 남은 Export Manager 정리. 단위 407개 OK(skip 2).
- 다음: 후보11 빌드·설치 → `%` 없는 특수문자 작업 폴더로 최소 환경 기본·WU 전체 재실행.
  USB를 다시 꽂으면 WU_09를 재확인한다.

## 2026-10-18 최종 설치판 검증 완료 (두 번째 PC)

목표였던 "최종 설치 EXE로 기본기능 전체와 실시간 WU 전체를 수행하고 WU_01/12/13 외 10건 PASS"를 달성했다.
상세 결과·해시는 [최종 검증 결과](docs/handoff-2026-10-18.md)에 있다.

- 빌드 도구: Inno Setup 6.7.3은 사용자 범위 설치, Nuitka 4.3은 Git 제외 `work/buildenv`에 설치했다.
- 수정: 콘솔 창이 최전면을 쥘 때의 로그인 실패(`4cabebd`), 한글 경로 빌드 중단(`f5e40fa`),
  WF09 3D Export 판정 범위(`516632c`). 설치판 실행 검증 도구 `tools/run_installed_suites.py`(`06842a9`).
- 최종판 후보8(`516632c`): 기본 PASS 23 / FAIL 2 / MANUAL 2, 실시간 WU PASS 10 / MANUAL 3.
  FAIL 2건은 기존 제품 결함(WF14 UPS, XIPL03 값 복귀)이다.
- 이 PC 설치 수명주기(새 설치·업데이트·제거·기본 경로 재설치, 새 셸·여러 CWD·App Paths)를 확인했다.
- 산출물 4개는 바탕 화면 `BellalunAuto 배포\1.0.0`, 실행 기록은 `D:\BellalunAuto 실행 기록\후보8-20261018_015140`(Git 제외).
- 남은 일: 개발 도구 없는 PC/VM, Windows 10, 다른 관리자 계정 UAC 검증. 제품 결함 수정 후 재확인.
- 승인 자료 manifest는 후보6 승인본과 같은 해시의 프로젝트 원본으로 `work/release-assets/approved-assets.json`에 재구성했다.

## 2026-10-15 두 번째 PC로 이관 병합

원래 PC에서 push하지 못한 `codex/bellalunauto-distribution`(HEAD `dcfefd3`)을 Git bundle로 받아
이 PC의 `main`(`25818ac`)에 fast-forward로 병합했다. bundle SHA256과 `git bundle verify`를 확인했다.

- 이 PC의 병합 전 미커밋 수정 6파일(2026-09 작업)은 git 제외 `work/pre-bundle-merge-backup-20261015/`에
  patch와 원본 사본으로 보존했다. 같은 파일의 후속판이 bundle 커밋에 들어 있어 작업 트리에는 bundle판을 쓴다.
- `AGENTS.md`는 키트 관리 블록(질문과 근거 보고)만 갱신했다.
- 이 PC 확인: `python -m unittest discover -s tests -p "test_*.py"` 360개 OK(skip 18),
  readiness failed 0(WARN `SPEC_OPEN_QUESTIONS`). 정식 후보6 빌드의 단위 424개 기록과는 실행 환경이 달라 대체하지 않는다.
- 이관 직후 이 PC에는 후보6 설치본·실행 증거·승인 내부 자산·Nuitka·Inno Setup이 없었다. Bellalun Service와
  `MSSQL$BELLALUN`은 실행 중이다.
- 이후 사용자가 원래 PC의 설치 폴더와 설치판 작업 폴더를 바탕 화면에 복사했다(git 제외, 공개 금지).
  설치 폴더 1007파일, EXE SHA256 `02c67e86…7e79`, build-info SHA256 `799cbf1f…ae2b`,
  BASIC 리포트 `Result_20261015_153714.json` SHA256 `50ecd908…021a`가 인계 값과 일치한다.
  setup 설치로 만든 것이 아니라 복사본이라 시작 메뉴·PATH·App Paths 등록은 없다.
- 작업 폴더의 WU 실패 증거: 15:38:55(PDT) `Evidence/ui/dialog_startup_1.png`(경고 아이콘·OK 대화상자 일부),
  15:39:06 `setup_startup_failed.png`(Viewer 로그인 화면, ID `service`, PW 빈칸)를 남겼다.
  `core/dicom_settings.py`의 `setup_all` 기동 단계(`flows.cold_start`→Patient 화면 확인)에서 실패한 것으로 보이며,
  예외 문구·기동 로그가 든 원래 PC의 `run-winupdate.log`는 아직 전달되지 않아 원인은 확정하지 않았다.
- 아직 없는 원래 PC 자료: 저장소 `work/`의 `final-suites-20261015-133607/`, `release-1.0.0-candidate6/`(setup/ZIP/SHA256SUMS),
  `approved-assets.json`, Inno Setup, `write_final_report.py`, `show_final_report.ps1`, 인계·체크포인트 md.

## 2026-10-15 인계: 후보6 기본 완료, WU 준비 실패

사용자가 여기까지 정리하고 다른 세션에서 이어가도록 요청했다. 최종 목표는 미달성이다.
다른 PC에서 읽을 재개 문서는 [세션 인계](docs/handoff-2026-10-15.md)다.
원래 PC의 상세 증거는 git 제외 `work/HANDOFF_20261015_candidate6.md`와
`work/checkpoint_candidate6.md`다. 최종 배포·결과 터미널 출력은 아직 하지 않았다.

- 정식 후보6 빌드 소스 `65f205ed05cb0c95bcdb997b6fb75098dc7c6631`,
  EXE SHA256 `02c67e86509901c4408abeb2126ee350bf3d4372aa5da9d4f2eafc779e987e79`.
  단위 424개·하위 238개, 산출물 감사 31항목, 설치 보존 7단계,
  guardian 3사례를 검증했다. CLI 자체진단 20 PASS다.
- GUI 3진입점과 버전·결과 폴더를 확인했다. 일반 권한 자체진단은 관리자 권한 부족을
  19 PASS/1 FAIL로 안내했고, 별도 승격 GUI의 두 진단은 각각 20 PASS였다.
  `work/final6-gui-validation-supplement.json`에서 권한별 근거를 구분한다.
- 동일 설치 EXE 기본 전체 13:36~15:37은 정상 종료했다. 27 TC: PASS 23 / FAIL 2 / MANUAL 2.
  `Result_20261015_153714.json`, 보존본 318파일 크기·SHA 일치와 첨부 120참조를 독립 확인했다.
  FAIL은 WF14 UPS 설정 미복원과 XIPL03 Recon/Syn 값 복귀다. 기본 원본 FAIL을 유지한다.
  `work/final6-basic-verdict-review.json`에는 기존 Step3/5 padding 한계도 구분했다.
- 이어진 live WU는 15:37~15:39 `DICOM_Server_Setup` 전제 준비 실패로 조기 종료했다.
  `Result_WindowsUpdate_20261015_153914.json`의 chain_completed=false이며 상태는 abnormal_exit다.
  중단 리포트의 0 PASS/9 FAIL/3 MANUAL/1 SKIP는 전체 수행 완료나 제품 9결함 확정이 아니다.
  준비 실패의 세부 원인은 아직 분석하지 않았다. WU10도 미수행이며 새 허용 제외로 삼지 않는다.
- 실제 실행·보존 근거: `work/final-suites-20261015-133607/verification.json`.
  관찰자와 제품 자동화 프로세스는 종료했다. 최종 WU 10 PASS는 아직 확인하지 못했다.
- 다음: WU 준비 실패 원인 분석 → 최종 EXE live WU 전체 완료/목표 확인 → 최종 문서·전달·출력.
  소스/EXE를 수정하면 정식 재빌드·설치 후 같은 새 EXE의 기본 전체와 live WU 전체를 재실행한다.
  기존 완료·실패 증거를 덮거나 이전 후보 결과를 최종 실행 결과로 사용하지 않는다.
- 별도 clean PC/VM·Windows 10·다른 관리자 계정 UAC는 미검증이다.
  이전 일반 push는 인증 실패였으며, 공개 README 등 최종 상태 반영과 정상 push 확인이 남았다.

## 2026-10-15 이전 진행 기록: 후보6 정식 빌드 전

사용자는 최종 설치 EXE로 기본기능 전체와 실시간 Windows Update 전체를 수행하고,
WU_01/12/13 기존 수동 범위 외 10건 PASS를 확인하도록 지시했다.
결과·전달 파일·남은 문제·commit/push는 바탕 화면의 한국어 문서와 터미널에 남긴다.

### 확인된 최신 실행

- 후보5 빌드 소스 `6065490be41f0e4eafd44db27a6e8d7ee3fc329e`, EXE SHA256
  `b15209428e8953aaa9c0dd4da69eb91b9467539075b0b4c34784771a20871d22`.
  실제 감사 31항목, 설치 보존 7단계, guardian 3사례, GUI 기동 경로·자체진단을 통과했다.
- 동일 설치 EXE 기본 전체 09:05~11:05: 27 TC, PASS 23 / FAIL 2 / MANUAL 2.
  선택 작업 폴더 `Reports/Result_20261015_110522.json`. WF01·XIPL_01/06은 PASS다.
  FAIL은 UPS 설정 미복원과 XIPL_03 Recon/Syn 값 기본 복귀다. 원래 제품 FAIL을 유지한다.
- 이어 실시간 WU 전체 11:05~12:45: 13 TC, PASS 9 / FAIL 1 / MANUAL 3.
  `Reports/Result_WindowsUpdate_20261015_124548.json`, live/chain_completed 확인.
  USB WU09는 PASS, WU10의 버튼 전용 `system.cs`·`system.my_settings` 화면을
  빈 설정값 목록으로 오판했다. 목표는 아직 미달이며 후보5를 최종 전달하지 않는다.
- 실행별 동기 보존본은 기본 300파일·WU 310파일 모두 크기·SHA256이 일치한다.
  `work/final-suites-20261015-090500/verification.json` 및 `snapshots/` 참조.
- XIPL_03의 Step3/5 미수행 padding은 이전 후보에도 있던 보고 번호 매핑 한계다.
  실제 Refresh/Preview/Apply PASS와 구분하며 FAIL check 7개를 제품 결함 7개로 세지 않는다.
  과거 회귀 변환과 live WU 경로도 구분한다. 독립 검토는 git 제외 work에 보존했다.

### 현재 수정과 다음 시작점

- 설정값 `pages`/`compare` 계약을 유지하면서 실제 패널 하위 콘텐츠의 렌더 관찰을 분리했다.
  버튼 전용 정상 화면은 콘텐츠를 입증하고, 빈 패널·숨김·외부·장식은 통과시키지 않는다.
  56페이지 및 빠른 탭 전환 24회는 유지한다. 전체 안전 단위 424개·하위 사례 238개와
  독립 리뷰를 통과했다. 실제 WU10 단독 검증의 56페이지·24회 전환은 PASS이며 DB는 변하지 않았다.
  실측 56개 관찰은 최종 크기 필터로 다시 확인했고 1픽셀 장식선만 있는 경우를 거부했다.
- 변경 파일: `core/setting_values.py`, `tests/winupdate.py`,
  `tests/test_setting_render.py`, `tests/test_winupdate_usb.py` 및 관련 사양 추적·변경 기록.
- 다음: 실제 WU10 단독 결과 확인 → 새 후보6 정식 빌드/설치/기동 검증 →
  동일 새 EXE 기본 전체 → 동기 보존 → live WU 전체 → 최종 판정/문서/전달/터미널 인계.
  세부 현재 작업은 git 제외 `work/checkpoint_candidate6.md`의 최신 절에서 확인한다.
- 원본 설정·체크리스트·사내 자료를 보존한다. 후보5 전달 파일은 git 제외 work로 옮겼다.
  사내 자산과 설치 파일은 공개 Git/Release에 넣지 않는다.
- 브랜치 `codex/bellalunauto-distribution`. 이전 일반 push는 GitHub 인증 부재로 실패했다.
  최종 관련 변경을 commit하고 일반 push를 다시 시도해 실제 결과를 따로 기록한다.
- 실제 검증은 개발 도구가 있는 동일 Windows 11 호스트다. 다른 관리자 계정 UAC,
  별도 clean PC/VM·Windows 10은 미검증이며 reduced PATH로 대체했다고 주장하지 않는다.

## 이전 인계

## 현재 목표

WU_09 USB Import의 되읽기 완료 신호와 Examined 재검색 교차 확인을 마무리하는 것이
현재 제품 작업이다. 2026-09-22 rollout은 SPEC/readiness 관리 체계만 도입하며 제품 기능을 추가하지 않는다.

## 현재 상태

`git status --short`를 2026-09-22 확인했다. 이전 세션의 WU_09 변경과 문서 변경이 남은 dirty tree다.
WU_09는 IMG 폴더 선택으로 목록 1행이 표시되는 것까지 실측됐지만,
중복 팝업의 Use existing data 이후 완료 검증은 끝나지 않았다.
2026-09-09 종료 시 Viewer를 사용자가 강제종료했다는 기록을 보존하며 현재 실행 상태로 단정하지 않는다.

## 진행 중

기존 WU_09의 `core/usb_media.py`, `core/export_manager.py`, `tests/winupdate.py` 변경은 보존한다.
되읽기 완료 검증 전 MANUAL을 PASS로 바꾸지 않는다.
이번 작업은 SPEC·CHANGELOG·진행 문서 정리와 readiness 검사다.

## 남은 작업

- WU_09 완료 신호를 실측하고 Examined 재검색으로 교차 확인한 뒤 판정을 결정한다.
  제품 실행 범위/시점은 사용자, 구현·검증은 자동화 유지보수 담당자가 맡는다.
- Install_01/02는 사용자/제품 QA의 승인 Release Note·OS Build 자료를 기다리며 기존 MANUAL/SKIP을 유지한다.
- WU 리포트의 원문 Step 접이식 영역을 채울지 사용자와 유지보수 담당자가 결정한다.
- Hub/Worker 진행률 소비 측 후속 확인과 제품 결함은 `NEXT_WORK.md`의 현재 우선순위를 따른다.

## 주요 결정

- USB Import 스캔은 경로 Edit 입력이 아니라 폴더 찾아보기 선택으로 시작한다.
  2026-09-09 대조에서는 IMG만 되읽혔으며 이전 DICOMDIR/IMG 가설은 정정됐다.
- 드라이브 루트·2단계 이상 경로를 거부하고 폴더 확인은 WM_COMMAND(IDOK)를 사용한다.
  컨트롤 ID 1102는 창 범위에 따라 의미가 달라 Import 창 범위로 제한한다.
- 제품 결함(UPS 설정 미복원, XIPL_03 3D 파라미터 복귀)의 FAIL을 완화하지 않는다.
- 기본기능/WU 리포트 제목·기준 문서·이유를 구분하고 비공개 자산/생성물은 공개 커밋에서 제외한다.
- 과거 상세 기록은 아래에 보존하고 현재 제품 인계의 기본 경로는 `NEXT_WORK.md`로 유지한다.

## 변경 파일

이번 작업: `SPEC.md`, `CHANGELOG.md`, `progress.md`.
기존 미커밋 제품 변경: `core/export_manager.py`, `core/usb_media.py`, `tests/winupdate.py`.
기존 문서/rollout 변경: `AGENTS.md`, `NEXT_WORK.md`, readiness/CI 및 spec-history.
최신 변경 목록은 `git status --short`로 다시 확인하며 이 작업에서 기존 변경을 커밋하거나 정리하지 않는다.

## 검증

- 마지막 안전 검사 원문 기록: 2026-09-09 `py_compile`, tools/check 계열,
  `pytest` 151 passed. 당시 실행 세부 명령은 원문에 적힌 범위 이상으로 추정하지 않는다.
- 기본기능 전체 회귀 기록: 2026-09-03 20:45~22:45, 29차, TC 27건
  PASS 23 / FAIL 2 / MANUAL 2(119.9분). FAIL 2건은 당시 알려진 제품 결함이다.
- WU 전체 체인 기록: 2026-09-07 19:17~20:57, TC 13건 PASS 9 / FAIL 0 / MANUAL 4 / SKIP 0.
  WU_09의 미완료 확인 상태를 이 과거 결과로 덮지 않는다.
- 2026-09-22 문서 readiness: 오류 0 / SPEC_OPEN_QUESTIONS 경고 1 / exit 0. 프로젝트 1개 검사, failed=0,
  gateFailures=0, checkerError=false. 미확정 항목의 영향과 담당자는 SPEC 13절에 명시했다.
- 이번 문서 작업에서는 Viewer/UI, baseline 복원, 전체 회귀를 실행하지 않았다.

## 다음 시작점

이 문서 → `git status --short` → `NEXT_WORK.md` 5절 ⑨와 6절 프롬프트 순서로 읽는다.
WU_09의 완료 신호 검증부터 이어가고, 완료 전 기존 미커밋 변경과 MANUAL 판정을 보존한다.
기존 기본기능/WU 검증과 사고 경위는 아래에서 필요한 날짜 절만 참조한다.

## 이전 상세 기록

2026-09-22 정리 전 본문을 아래에 보존했다. 09-07/09-08의 USB 포맷/스캔 가설은
09-09 정정 기록보다 우선하지 않는다. 고유 운영 사실을 삭제하거나 Git 이력에만 맡기지 않았다.
### Progress Checkpoint

#### 2026-09-09 WU_09 USB Import 되읽기 — 트리거 확정, 완료 확인만 남음

**목표**: 세 세션째 "Import Study 목록 0행"으로 막혀 있던 WU_09 되읽기를
자동화한다. 사용자가 수동으로 성공하는 화면(`D:\BellalunWU09_imgonly` 선택
→ 1행 표시)을 보여주면서 재개했다.

##### 완료

- **원인 확정**: 경로 Edit(2065)에 `set_text`+Enter 로는 **스캔이 시작되지
  않는다**(루트/리프 무관, 대기 90초까지 전부 0행). 지난 세션들이 "폴더
  트리로도 실패"라고 적은 시도들도 실제 코드는 `set_import_path`(=set_text)를
  쓰고 있었다. 진짜 트리거는 **폴더 찾아보기(2063)로 폴더를 골라 확인**하는
  것이다.
- **절차 전체 라이브 재현**: 드라이브 선택(2062, 항목이 화면과 역순이라 y
  정렬 필수) → 폴더 찾아보기 → 루트 노드 클릭으로 트리 포커스 확보 → Down N
  → WM_COMMAND(IDOK) → 목록 행 클릭 선택 → Import → 중복 팝업에서
  "Use existing data"(1101). `D:\BellalunWU09_imgonly` 로 1행 표시까지
  자동화로 확인했다.
- **포맷 결론 정정**: 같은 절차로 대조한 결과 **IMG 포맷만 되읽힌다** —
  plain DICOM 0행 / DICOMDIR+PortView 0행 / IMG 1행. 2026-09-08 의
  "DICOMDIR 이 필요하다, IMG 는 대상 아니다"는 반대였다(그때는 경로 지정
  방법 자체가 틀려 어떤 포맷도 0행이었다).
- **코드**: `core/usb_media.py` 재작성(select_drive / select_import_folder /
  select_row / duplicate_patient_popup / resolve_duplicate_patient /
  import_window / wait_for_rows / attempt_import, 실측 근거 docstring 포함),
  `core/export_manager.py::select_only_format` 신설(File Format 은 독립
  체크박스라 이전 선택이 함께 나간다), `tests/winupdate.py` 를 1단계 폴더
  (`USB_EXPORT_FOLDER`) + IMG 단독 Export + 매 실행 폴더 비우기로 정렬.
  `py_compile` / `tools/check_*` / `pytest 151 passed` 통과.

##### 남은 작업 (다음 세션 시작점)

되읽기 **완료 확인** 한 단계. 사용자 요청으로 "Use existing data" 직전에
멈춰서, 그 이후 제품이 보여주는 완료 신호를 아직 실측하지 못했다.
Examined 재검색으로 검사가 늘었는지 교차 확인하는 단계를 붙이고
`_wu_09` 를 MANUAL → PASS 판정으로 바꾼 뒤 `run-winupdate` 라이브 확인.
상세는 NEXT_WORK.md 5절 ⑨ 와 6절 프롬프트.

##### 사고와 대응 (재발 방지)

- **C:\ 전체 스캔을 한 번 일으켰다.** `BFFM_SETSELECTIONW`(WM_USER+103)를
  크로스 프로세스로 보내 임의 깊이 경로를 지정하려 했으나 이 다이얼로그가
  **무시**했고, 초기 선택인 C:\ 루트가 그대로 IDOK 됐다. "Find Images
  (n/710)" 가 17분 넘게 돌았고 그동안 Close 가 전혀 먹지 않았다. 스캔이
  끝난 뒤 정리했고 **아무것도 Import 하지 않았다.** → `select_import_folder()`
  가 드라이브 루트와 2단계 이상 경로를 예외로 거부한다.
- **`C:\새 폴더` 가 생성됐다.** 폴더 다이얼로그가 열린 직후 트리에 포커스가
  없는 줄 모르고 Home/Down 을 보냈더니 포커스가 "새 폴더 만들기" 버튼으로
  갔고, 확인하려고 누른 Enter 가 그 버튼을 눌렀다. 빈 폴더를 확인하고
  삭제했다. → 확인은 Enter 가 아니라 **WM_COMMAND(IDOK)** 로 보낸다.
- **1102 가 두 의미다.** 중복 팝업의 "Not change data" 와 Import Study 의
  Close 가 같은 ID 다. → `close_import_dialog()` 는 `import_window()` 로 창
  범위를 한정해서 찾는다.

##### 미커밋

위 세 파일 변경은 **아직 커밋하지 않았다** — 되읽기 완료 확인까지 마치고
한 번에 커밋한다. Viewer 는 세션 끝에 사용자가 강제종료했다.

---

#### 2026-09-07 Windows Update 체크리스트 자동화 — 완료(라이브 전체 체인 PASS 9/FAIL 0/MANUAL 4)

**목표**: `../Windows Update 호환성 검증 Checklist_Bellalun Viewer_R-25-782.xlsx`
(시트 `Checklist`, TC_WindowsUpdate_01~13)를 신규 TC 없이 기존 기본기능/XIPL
자동화 재사용 + 얇은 매핑 계층으로 자동화. 상세 요구사항은 이 작업을 지시한
프롬프트(세션 로그) 참고 — 결정사항 1~7 전부 사용자 확정.

##### 완료

- **매핑/리포트 인프라**: `tests/winupdate.py`(공유 매핑 표 `build_wu_results()`,
  `run()`/`--from-regression` 양쪽이 공유), `core/winupdate_report.py`(K열
  삽입 + `Result\n<MM/DD>` + Pass/Fail/Manual 리터럴 + 1~4행 실측 + Issues
  탭), `run.py`에 `run-winupdate`(+`--from-regression <path>`) CLI 추가.
  `python run.py run-winupdate --from-regression Reports/Result_20260903_224518.json`
  로 라이브 검증 완료 — `Reports/WindowsUpdate_Checklist_Result_20260907_191627.xlsx`
  생성 확인(K열 정상 삽입, 기존 L~S 밀림, 1~4행 실측값, Issues 탭 3건).
- **WU_01/12/13 MANUAL** — `TC_Basic_WorkFlow_16` 패턴으로 기록. WU_01은
  Install_01/02 판정 + `sysinfo.pc_info()`/`os_update_info()` 실측을 참고
  근거로 첨부.
- **WU_02** — `tests/workflow01.py`에 **Age** 대조 추가(생년월일·Scheduled
  Date 기준 독립 계산, 라이브 검증 PASS "46"). **Scheduled Date/Time도
  2026-09-08 완료** — 사용자 힌트(`Setting > Patient > Patient List >
  List Show Item`에 "Scheduled Study DateTime" 추가) 그대로 확인됨(기본
  꺼짐). `core/flows.py::ensure_scheduled_datetime_column()`(멱등 — 이미
  켜져 있으면 안 바꿈)와 `scroll_study_list_right()`(카드 열 전체 폭이
  화면보다 넓어 오른쪽으로 스크롤 필요, owner-draw라 고정 클릭 수 대신
  "기대 날짜 보일 때까지 조금씩 스크롤 반복" 방식)를 추가하고
  `tests/workflow01.py` Step 1에서 Patient List 카드를 OCR로 읽어 대조한다
  (Edit Information의 `study_datetime`은 Scheduled가 아니라 실제 Study
  일시라 여전히 안 씀). **라이브 검증: `TC_Basic_WorkFlow_01` 전체 PASS**
  (`Scheduled Date` 항목 포함, `Reports/Result_20260908_120515.json`).
  이 대조는 `r.add(..., stop=False)`로 넣어 owner-draw OCR 특유의 간헐
  실패가 TC 전체를 중단시키지 않게 방어해 뒀다.
- **WU_03** — Rotation 컨트롤 ID 실측(CW=1120, CCW=1121 — Expand 패널 안,
  스크린샷으로 라벨 확인). `core/viewer_tools.py::apply_tool_sequence`에
  Select(1111, 기존 실측)+Rotate CW/CCW 추가, Select는 화면 변화 대신
  `screen.radio_selected` 활성 표시로 판정. 라이브 검증 전부 PASS(2D pane).
  WF_02도 함께 고도화(Step 6/7에 반영, 사용자 승인).
- **WU_04/06/07/08/05/11**: 재사용 매핑 구현 + 결함 예외 처리(`_copy_checks`의
  `abort_keyword` — 알려진 결함이 유일한 FAIL 원인일 때만 cascading abort
  기록도 함께 제외, 다른 FAIL이 있으면 안전하게 남김). `--from-regression`
  라이브 테스트에서 WU_11이 UPS 결함 2건 모두 정상 제외되고 PASS로 전환됨을
  확인. WU_05는 이번 회귀 스냅샷의 실제 다른 원인(Step 1 조기 중단)이 그대로
  FAIL로 남는 것도 확인(설계대로 — 알려진 결함이 아닌 FAIL은 안 가린다).
- **⚠ 아래 09-07/09-08 절의 WU_09 서술은 2026-09-09 에 정정됐다** — "DICOMDIR 포맷이 필요하다"와 "경로 Edit 설정으로 경로가 지정된다"는 둘 다 틀렸다. 실제로는 폴더 찾아보기로 골라야 스캔이 시작되고, 되읽히는 포맷은 IMG 뿐이다. 맨 위 2026-09-09 절과 NEXT_WORK.md 5절 ⑨ 를 기준으로 삼아라.

- **WU_09**: `core/usb_media.py` 신규 — `find_usb_drive()`(이동식 드라이브
  자동 탐지, 없으면 SKIP), USB Export는 `core/export_manager.py` 그대로
  재사용(경로만 USB로). **USB Import 되읽기는 미해결** — Import Study
  대화상자(2184, 컨트롤 ID 전부 실측: 2062 드라이브/2065 경로 Edit/2063
  폴더찾아보기/2066 결과 목록/2064 Import/1102 Close)까지는 열었지만, 목록에
  실제로 행이 채워지는 트리거를 이 세션에서 못 찾았다(경로 Edit
  set_text+Enter 시도, 네이티브 폴더 다이얼로그 경로 주입 시도 모두 실패 —
  드라이브 드롭다운 C:\\/D:\\/E:\\ 선택이 진짜 트리거일 가능성이 높으나
  항목 컨트롤 ID 미확정). 현재 코드는 목록이 비어 있으면 **추측으로 Import를
  누르지 않고 MANUAL로 남긴다**(안전한 실패). 상세 실측 기록은
  `core/usb_media.py` 모듈 docstring.
- **WU_10**: 신규 구현(`tests/winupdate.run_setting_display`) —
  `setting_values.read_all` 전수 순회 그대로 재사용 + "탭 빠른 클릭"
  서브체크 신규(인접 그룹 A→B→A, 0.15초 간격, 활성표시+콘텐츠렌더 확인).

##### 라이브 전체 체인 실행 결과 (완료 — 2026-09-07 19:17~20:57, 99.8분)

`python run.py run-winupdate` 를 Start-Process로 완전히 분리된 백그라운드
프로세스로 띄워 끝까지 완주했다(세션 종료와 무관하게 계속 동작 — 로그
`Reports/winupdate_live_20260907.out.log`, 산출물
`Reports/WindowsUpdate_Checklist_Result_20260907_205703.xlsx`).

**TC 13건: PASS 9 / FAIL 0 / MANUAL 4 / SKIP 0. 검증 215개: PASS 209 / FAIL 0 /
MANUAL 4 / SKIP 2. 자동화·제품 결함 전부 0건(FAIL 없음).**

| WU TC | 판정 | 비고 |
|---|---|---|
| 01 | MANUAL | 설계대로(참고 근거 첨부) |
| 02 | PASS | Age 대조 포함(46 일치) |
| 03 | PASS | Select+Rotate CW/CCW 신규 추가분 라이브 확인 |
| 04 | PASS | |
| 05 | PASS | XIPL_03 Step 9 알려진 결함, 이번 실행에선 재현 안 됨(아래 참고) |
| 06 | PASS | |
| 07 | PASS | |
| 08 | PASS | |
| 09 | MANUAL | **USB 드라이브 실제 인식(D:\\), Export 완전 자동 PASS.** Import 되읽기만 안전하게 MANUAL(추측 클릭 안 함) |
| 10 | **PASS** | 신규 구현 첫 라이브 실행 — Setting 56페이지 전수 순회 PASS, "탭 빠른 클릭" 24/24 전부 PASS |
| 11 | PASS | |
| 12 | MANUAL | 설계대로 |
| 13 | MANUAL | 설계대로 |

**Issues 탭 정확도 개선(라이브 실행 후 발견)**: `_attach_known_issues`가
title 매칭만으로 이슈를 실었는데, 이번 실행처럼 알려진 결함(UPS/3D 파라미터)
이 실제로는 재현되지 않은 회차에도 "기존 알려진 제품 결함"으로 실려 오해를
줄 수 있었다. **실제 그 check가 FAIL일 때만** Issues 탭에 싣도록
`tests/winupdate.py::_attach_known_issues`를 고쳤다(status=="FAIL" 조건
추가). `--from-regression`으로 결함이 실제 FAIL이었던 과거 스냅샷 재검증 —
issues 3건 그대로 유지됨을 확인(회귀 없음).

##### 남은 작업 / 사용자 판단 필요

1. ~~WU_02 Scheduled Date/Time 표시 위치~~ — **2026-09-08 완료**(위 참고).
2. **WU_09 USB Import 되읽기 — 핵심 원인 확정, 가설 (a)(b) 기각(2026-09-08
   이어서 조사)**. Import Study는 **DICOMDIR 포맷이 있어야만 인식한다** —
   일반 "DICOM" 포맷 Export(기존 WF_09/USB Export가 쓰는 것)는 DICOMDIR을
   안 만든다. `core/export_manager.py`에 `FORMAT_DICOMDIR`/`select_format()`/
   `set_portable_viewer()` 헬퍼를 정식으로 추가했고(`FORMAT_DICOM`도
   1008로 정정 — 기존 1009는 실제로 DICOMDIR 버튼이었다), `tests/
   winupdate.py::run_usb_export_import`가 Export 전에 이 둘을 선택하도록
   반영했다. 라이브로 DICOMDIR+Portable Viewer Export(Autorun.inf+
   PortView\ 전부 생성 확인, MG 데이터 정상)한 뒤, Import 경로를 정확한
   리프 폴더로 설정하고 **90초 폴링**, **드라이브 드롭다운(2062)을 경로
   설정보다 먼저 선택**하는 조합, **드라이브 우선 선택 + 키보드 트리 탐색**
   조합까지 전부 시도했지만 Import 목록(2066)은 항상 0행이었다 — **스캔
   대기 부족(가설 a)과 Autorun.inf/PortView 부재(가설 b)는 원인이 아니라고
   결론**. 남은 후보 (c) USB가 Import 기능이 요구하는 미디어 종류로 인식
   안 될 가능성, (d) DICOMDIR 스캔이 Windows AutoPlay/미디어 삽입 이벤트에
   매여 있어 이미 꽂힌 드라이브를 UI로 사후 탐색해선 트리거가 안 될 가능성
   — 상세는 `NEXT_WORK.md` 5절 ⑨ 참고.
   - **환경 버그 발견·수정(WU_09와 별개, 전체 라이브 자동화에 영향)**: 이
     조사 중 Windows **작업표시줄 자동 숨김이 꺼져 있어** Viewer 메인 메뉴
     버튼(화면 좌하단)을 작업표시줄이 덮어 클릭이 새는 문제를 발견했다
     (`blocking_window()`는 셸 창을 의도적으로 "가림 아님"으로 봐서 못
     잡는 케이스). `core/ui.py::taskbar_autohidden()`(SHAppBarMessage로
     임시 자동 숨김, 종료 시 원상복구 — `foreground_unlocked`와 같은
     패턴)을 추가하고 `run.py`의 `__main__`에서 함께 걸었다.
   - **2026-09-08 추가 조사(사용자 요청 — IMG 옵션, USB 드라이브 재확인)**:
     USB는 이번에도 **D:\ (VXvue1, REMOVABLE)** 로 동일하게 인식됨을 재확인
     (참고로 E:\ 는 빈 CD-ROM 드라이브). Export Manager의 File Format
     버튼은 **라디오 그룹이 아니라 독립 체크박스**임을 실측으로 정정했다
     (DICOMDIR+IMG를 동시에 체크한 채 Export하면 DICOMDIR 패키지에 IMG
     원본 덤프가 추가로 섞여 들어간다 — 이전 docstring이 "라디오 방식
     그룹"이라 잘못 적어 뒀던 것을 고쳤다). **IMG 단독**(DICOMDIR/Portable
     Viewer 전부 해제, `.img`+`.txt` 원본 픽셀 덤프만 생성 확인)으로도
     Import 목록은 여전히 0행 — **사용자의 IMG 가설도 기각.** 또한 Import
     목록이 0행인 채로 "Import" 버튼(2064)을 눌러 보면 "No study to
     import." 안내만 뜨고 숨은 스캔 트리거는 아니었다. 지금까지 DICOMDIR
     단독/DICOMDIR+Portable Viewer/DICOMDIR+IMG/IMG 단독 네 조합 모두
     실패 — **Export 포맷 조합이 원인일 가능성은 사실상 소진됐다**, 남은
     유력 후보는 NEXT_WORK.md ⑨의 (c)/(d)(USB 미디어 인식/AutoPlay 트리거)
     뿐이다.
3. ~~WU_09 xlsx 자동 기록 정책 재검토~~ — **2026-09-08 사용자 확정, 구현
   완료**. 기존 K열(Result) 삽입 방식은 유지하고, **K열 바로 옆에 L열
   (Comment)을 추가로 삽입**해 Fail/Manual TC에만 그 판정을 끌어낸 check의
   note(짧게, 최대 3개) 를 적도록 `core/winupdate_report.py`를 고쳤다
   (`_reason_for()` 신규 — Pass/Skip은 비워 둔다). 기존에 이미 있던 공용
   "Comment" 열(여러 회차가 공유하는 수기 메모)은 그대로 두고 자동화가
   덮어쓰지 않는다 — 이 새 L열과는 별개다. `--from-regression Reports/
   Result_20260903_224518.json`로 재생성해 FAIL 1건(WU_05)·MANUAL 3건
   (WU_01/12/13)에 Comment가 채워지고 PASS/SKIP 행은 비는 것을 확인했다.
   상단 1~4행 OS/OS Version/OS Build/Viewer Version 실측 기록은 이미
   2026-09-07에 구현돼 있었다(`_winupdate_env()`) — 그대로 유지.
4. **HTML/TXT 리포트 공통 버그 2건 수정(2026-09-08, 사용자 지적 — WU 리포트를
   보다가 발견)**. `core/result.py::_render_html`이 이제까지 **모든**
   리포트(기본기능/WU 공용)의 제목·기준 문서 줄을 기본기능 체크리스트로
   하드코딩하고 있었다 — WU 리포트를 열어도 "Bellalun_Viewer_기본기능_
   Checklist_개정본.xlsx (시트 개정 TC)"가 찍혔다. `meta`에
   `report_title`/`source_doc`/`source_sheet`를 넣으면 덮어쓰도록 고치고
   (기본값은 기존 기본기능 문구 그대로라 하위호환), `run.py::
   _finish_winupdate`가 WU용 값을 채운다. 라이브로 재생성해 WU 리포트는
   "Windows Update 호환성 검증 Checklist...xlsx (시트 Checklist)", 기본기능
   리포트는 기존 문구 그대로임을 확인했다.
   또한 TC별 "소요 시간 분해"(Step 단위 breakdown)를 완전히 없앴다 — Step
   자체는 순식간에 끝나 항상 0초에 가깝게 찍혀 정보 가치가 없다는 지적.
   `TCResult.add()`가 더 이상 Step 단위 타이밍을 재지 않고(`_step_cursor`
   갱신만 유지 — `finalize()`의 종료 시각 보정용), HTML `<details>소요 시간
   분해</details>`와 TXT `[소요시간]` 블록을 통째로 뺐다. TC 전체 소요시간은
   기존처럼 TC 헤더/요약표에 그대로 남는다(추가 구현 불필요, 원래 있었다).
   `record_timing()`(DB/화면전환 대기처럼 의미 있는 wait 기록, `tests/
   test_performance_waits.py`가 검증)은 건드리지 않았다 — 리포트 표시만
   껐을 뿐 JSON(`timings` 필드)에는 그대로 남는다. 이 테스트가 옛 HTML
   문구를 검증하고 있어서 새 동작(그 문구가 **없어야** 함)에 맞춰 함께
   고쳤다.
5. **"이런 유형의 버그" 전수조사(2026-09-08, 사용자 요청) — 같은 클래스로
   2건 더 발견, 전부 수정.** 항목 4의 HTML 수정이 TXT/CSV는 놓치고 있었다
   — 재생성해 확인해 보니 WU 리포트의 TXT/CSV 머리글도 여전히 "Bellalun
   Viewer 기본기능 자동화 결과"로 찍혔다. `write_txt()`에 `report_title`
   인자, `write_reports()`의 CSV 헤더에 `meta["report_title_short"]`를
   추가해 고쳤다(`_finish_winupdate`가 WU용 문구를 채운다. 기본값은 기존
   기본기능 문구라 하위호환). 또 하나 — **모든** 리포트(WU뿐 아니라 회귀/
   개별 TC 전부)의 "실행 명령" 줄이 `sys.argv[1:]`만 이어붙여
   `python run.py`가 빠진 채(`python run-winupdate ...`, `python
   portability-check ...`) 찍히고 있었다 — 그대로 복사해 실행하면 실패하는
   명령이었다. `_report_meta`/`_finish_winupdate` 두 곳이 나란히 같은
   실수를 하고 있어서 `run.py::_command_line()` 공용 헬퍼로 합쳐 고쳤다.
   라이브로 4개 형식(HTML/TXT/CSV) × 2개 컨텍스트(기본기능/WU) 전부
   재생성해 문구·명령이 맞는지 확인했다.
   **낮은 우선순위로 남겨 둔 것** — WU 리포트의 TC별 "기준 문서 원문"
   접이식 섹션(Precondition/Step Description/Expected Result 원문 인용)은
   `meta["checklist"]`가 기본기능 체크리스트만 담고 있어서 WU TC에는 항상
   비어 있다(`_step_context`가 조용히 빈 문자열을 돌려줘 죽지는 않는다).
   틀린 내용이 나오는 버그는 아니고 — 각 Step의 `expected`/`actual`/`note`
   (재사용한 기본기능/XIPL TC의 실제 값)는 정상적으로 나온다 — WU 체크리스트
   자체 원문을 이 자리에 채우려면 `winupdate_report`쪽에 `read_tc_rows`류
   함수를 새로 만들어야 하는 설계 결정이 필요해 손대지 않았다. 필요하면
   다음에 논의.

##### 변경/신규 파일

`tests/winupdate.py`(신규 — 매핑 표, 2026-09-08 이어서 DICOMDIR 포맷/
Portable Viewer 선택 추가), `core/winupdate_report.py`(신규 — WU
xlsx writer), `core/usb_media.py`(신규 — USB 탐지+Import 시도), `run.py`
(`run-winupdate`/`--from-regression` CLI, 2026-09-08 이어서 `__main__`에
`taskbar_autohidden()` 추가), `core/sysinfo.py`(`os_update_info` 추가),
`core/viewer_tools.py`(Select/Rotate CW/CCW), `tests/workflow01.py`
(Age/Scheduled 대조 추가 — WF_01 자체도 고도화됨), `core/export_manager.py`
(2026-09-08 이어서 — `FORMAT_DICOM` 1008로 정정, `FORMAT_DICOMDIR` 등 File
Format 상수 전부 추가, `select_format()`/`set_portable_viewer()` 신규,
File Format이 체크박스임을 반영해 docstring 정정), `core/ui.py`(2026-09-08
이어서 — `taskbar_autohidden()` 신규, 환경 버그 수정), `core/winupdate_report.py`
(2026-09-08 이어서 — L열 Comment 신규, `_reason_for()` 신규), `core/result.py`
(2026-09-08 이어서 — `_render_html`/`write_txt`/CSV 헤더 제목·기준문서 meta
파라미터화, Step 단위 타이밍 기록/렌더링 제거), `tests/test_performance_waits.py`
(2026-09-08 이어서 — 제거된 "소요 시간 분해" 문구 검증을 "없어야 함" 검증으로
갱신), `run.py`(2026-09-08 다시 이어서 — `_command_line()` 공용 헬퍼 신규,
`_report_meta`/`_finish_winupdate` 두 곳의 "실행 명령에 run.py 누락" 수정).

---

#### 2026-09-07 저장소 경로 이전 (기능 변경 없음)

- OneDrive 동기화를 해지하고 알려진 폴더 리디렉션(`Desktop`/`Personal`/`My Pictures`
  → `%USERPROFILE%\OneDrive\...`)을 해제하면서 프로젝트 루트를
  `C:\Users\ksj74\OneDrive\Desktop\자동화\Bellalun Viewer` → **`C:\자동화\Bellalun Viewer`**
  로 옮겼다. 저장소 안의 산출물·기준 문서 경로는 모두 `ctx.root`/`__file__` 상대라
  **기능 코드 변경은 없다.**
- 갱신한 것: `config.json > checklist_xlsx`(다른 PC 경로가 박혀 있어 `""`로 비움 —
  `core/checklist.source_path`가 상위 탐색으로 스스로 찾는다), `core/dbreset.py`
  docstring 근거, `NEXT_WORK.md` 1절, `..\프로젝트_상세.md`(+`.html` 재생성),
  원격 자동화의 `C:\AI-Worker\config\worker.json`(`bellalun` 경로).
- 부수 효과 2건(둘 다 개선):
  - 프로필 밖으로 나가 SQL Server `NT AUTHORITY\LOCALSERVICE`가 `Baseline\`을 직접
    읽을 수 있게 됐다. `core/dbreset.py`의 복사-후-RESTORE는 PC 독립성 때문에 유지.
  - `tests/install_package_flow.py`의 `~\Desktop` 후보가 리디렉션 때문에 **실존하지
    않는 경로**를 보고 있었다(`C:\Users\ksj74\Desktop`가 없었음). 이제 정상화.
- `tests/install_package.install_log_dir()`는 `SHGetFolderPathW(CSIDL_PERSONAL)`로
  Documents를 셸에 물으므로 코드 변경이 필요 없었다. 실체 데이터(`Bellalun\InstallLog`)
  를 `OneDrive\문서` → `C:\Users\ksj74\Documents`로 함께 옮겨 기존 로그 3건 유지 확인.

#### 2026-09-03 현재 상태

- **29차 전체 회귀 완료(2026-09-03 20:45~22:45, `Reports/Result_20260903_224518.json`,
  119.9분): PASS 23 / FAIL 2 / MANUAL 2. 자동화 결함 0건.** 남은 FAIL 2건(`WF_14`
  UPS 설정 미복원, `XIPL_03` 3D 파라미터 기본값 복귀)은 전부 이미 알려진 **제품
  결함**이라 완화하지 않는다. 28차와 TC 판정 완전히 동일 — 이번 회차에 추가한
  변경(아래)이 전체 회귀 경로에서 회귀를 만들지 않음을 확인했다.
- 이번 회차에 한 일:
  - `TC_XIPL_compatibility_07`에 "새 3D Preset이 그 시점 General Default를
    물려받는가" 보강 체크 추가(`probe-preset3d`로 3D-N/3D-W Preset 컨트롤
    ID 실측 → `core/flows.py` 상수화 → `tests/xipl_flows.py`에 헬퍼 신설).
    `automation_scope.json`의 gap 해소로 정정.
  - `run-sys3d`/`run-ui`에 남은 고정 대기를 상태 기반(`wait_new_group`/DB 행
    수 대기)으로 전환.
  - `TC_Basic_WorkFlow_13`(계정 권한별 Setting 노출)은 이미 2026-08-20에
    완전 자동화돼 있었음을 발견 — docstring/`--help`만 stale이라 문서만 정정.
  - stale 브랜치 `agent/add-next-task-handoff`는 이미 존재하지 않음 확인.
  - 회귀 진행률을 `work/regression_state.json`에 남기는 Hub/Worker 연동
    착수(커밋 `65d44d5`). `AI-Remote-Control`은 `hongmin3/AI-Remote-Control`
    (GitHub, private)로 위치 확인 — 이 세션 자체가 그 Issue(#24)로 디스패치된
    것이었다. `background_watch.py`의 실제 소비 로직은 아직 안 봤다.
  - 전체 회귀는 `tools/run_regression.py`를 완전히 분리된 백그라운드
    프로세스로 띄워 수행했다(세션 종료와 무관하게 계속 동작).
- 문서 동기화: `../프로젝트_상세.md`(B.34~B.36, 5.1/5.2절·기준 시점을 29차로)
  → `render_docs.py` → `README.md` → `NEXT_WORK.md` → 이 문서 순으로 갱신했다.

> 장시간/대규모 작업 후 현재 상태만 갱신한다. 완료 이력을 누적하지 않는다.

- 진행 중 작업: 없음. 이번 회차 요청 사항(WF_13/P1/P2/전체 회귀) 전부 완료.
- 남은 작업(사용자 자료 대기):
  - `Install_01`/`Install_02`는 사용자가 자료(Release Note, OS Build 목록)를
    줄 때까지 건드리지 않음(MANUAL/SKIP 유지).
  - Hub/Worker 연동 후속 — `AI-Remote-Control` 저장소의 `background_watch.py`
    실제 소비 로직 확인, 다음 필요 항목 설계.
- 알려진 문제: `NEXT_WORK.md` 3절 참고(제품 결함 3-A/XIPL_03, 간헐 증상
  3-B/3-C — 전부 자동화 결함 아님, 29차에서도 회귀 없음).

## 2026-09-22 — 프로젝트 킷 rollout 안전 검증 기록

기존 기록은 그대로 두고 이 절만 덧붙인다. 이 결과는 **문서·구조·안전 테스트** 범위이며
제품 UI·실기 동작 검증을 대신하지 않는다.

- 안전 테스트(외부 시스템·DB·시험 서버 미조작): `python -m unittest` 151개 통과
- 완료 검사: `node .project-check/project-readiness.js .` → `failed=0`
- 공통 지침 workflow: `spec-workflow: v3` (사양 두 층 구조 — `SPEC.md` 인덱스 + `specs/<기능>.md`)
- 증거 로그: 워크스페이스의 `.project-kit-rollout-backup/20260922-121838/verification/`
  (저장소에는 담지 않는다 — 로컬 경로와 실행 기록이 들어 있다)
- 미커밋 제품 변경은 건드리지 않았다. 커밋 범위는 사용자가 정한다.

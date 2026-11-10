# 1.0.4 후보의 자동화 실패 경로 보강

run542의 1.0.3 실제 설치판 결과를 기준으로 수정했다. VXvue의 컨트롤 재조회·영역 판독·상태 대기·실패 진단 원칙을 참고했으며 VXvue 코드·제품 ID·시각 임계값을 그대로 이식하지 않았다.

| 관찰된 경로 | 수정 | 코드에서 확인할 것 |
|---|---|---|
| WF03/08·WU08의 잘린 OCR 경쟁 후보 | 모든 후보를 보존하며 각 행을 온전히 드러내고 한 번 캡처, 선택 직전 재조회 | 잘린 행 회복, 같은 문구 경쟁 거부, HWND 중복 제거, 소실·ID 변경·스크롤 한계 실패 |
| WU09 검색 팝업 미확인 | Viewer PID 안에서 콤보에 인접한 유일한 ItemList와 필수 Control ID를 제한 대기 | 지연, 다른 팝업, 경합, 항목/필수 ID 미등장 시간초과 |
| WF14/WU11의 빈 Print Overlay 목록 | DB 전체 항목이0일 때만 존재하는 Position 목록에 기대0 전달 | 없는 컨트롤은 실패 유지, DB 미확인·실제 항목 존재 시 기존 전수 열거 유지 |
| XIPL07/WU05 Post Reconstruction 미확인 | 버튼 준비와 두 필수 컨트롤의 동시 준비를 제한 대기, 이미 열렸으면 재클릭 생략 | 부분 상태 거부, 지연 준비, 시간초과, 클릭1회 |
| WF08 OCR 증거가 CWD 밖에 분산 | Context의 Evidence/OCR 기본값과 WF08 명시 경로 | CWD 변경에도 같은 실행 증거 아래 저장 |
| XIPL05 F8 촬영 로그 미확인 | 대기 단계·영역·소요·로그 바이트·시간 필터 후 행 수 보존 | 원문 복제 없이 실패 유지; 실제 원인 해결은 미확정 |

OCR 유사도0.85·차순위차0.15·신뢰도35·최대4판독, 짧은 문구 완전일치, 미판독 경쟁 후보 거부를 유지한다. WF14 UPS·XIPL03 Step9의 기존 허용 목록과 수동 범위는 바꾸지 않았다. 새로운 실패를 허용 목록에 넣지 않는다.

## 코드 검증과 실측의 경계

재현 테스트의 실패를 확인한 후 수정했고 독립 검토에서 중복 HWND 재조회 결함을 추가로 재현·수정했다. 전체 단위시험과 정적 검사 결과는 progress.md에 기록한다. 스크롤과 팝업의 실제 제품 동작, DB 저장값·필름 표시, USB 완료는 코드 시험만으로 통과 판정하지 않는다.

별도 worktree 시험903 passed/3 skipped 후, 정규 main에서는 기존 Inno6.7.3 위치를 명시해906 passed / 0 skipped / 293 subtests를 확인했다. 고정된 로컬 Inno 경로만 찾던 시험에 BELLALUN_TEST_ISCC 환경변수 선택을 추가했으며 기존 컴파일러로 버전 probe·설치 스크립트 컴파일 검사도 실제 수행했다. 바이트코드 컴파일·정적7종·추적성 TC50건 위반0·SPEC readiness·workspace gate를 확인했다(기존 경고 유지). 독립 검토에서 추가 Critical/Important는 발견하지 못했다.

빌드 당시에는 기존1.0.3 설치판·Setup·ZIP·원본 보고서·증거를 보존했고 새 후보의 UI 실행은 미승인이었다. 1.0.3의 전체 실행과 거부된 게이트는 [과거 검증](ocr-release-validation.md)을 따른다. 이후 승인된1.0.4 설치·두 전체 실측과 현재 상태는 아래 결과를 따른다. 배포 PASS가 아니다.

## run546 후보 빌드와 산출물 검증

기존 분리 빌드를 그대로 인수했으며 새 빌드·프로세스 종료·제품 소스 변경은 하지 않았다. 2026-11-10 08:13:57~08:41:44 KST(27분47초), 감독 상태 finished/exit_code=0이다. Nuitka의 EXE 생성 성공과 Inno의 Setup 컴파일 성공(37.015초)을 확인했다.

소스는 `98477088cafb9ad4e1cfcfeee955bd934cf1227e`, `source_dirty=false`, compile/tests 생략은 모두 false다. Python3.12.10·Nuitka4.3·GCC15.2.0·Inno6.7.3을 그대로 사용했다. `build-info`의 PE subsystem2를 실제 EXE 헤더에서도 확인했다. `release_gate.status=candidate`, `passed=false`와 후보 표식을 유지한다.

### 산출물 위치와 SHA-256

전달 후보는 `release/1.0.4/`의 Setup·build-info·SHA256SUMS·후보 표식·설치용 ZIP이다. standalone EXE는 `work/release-1.0.4-run546/BellalunAuto-1.0.4/`에 있으며 설치하거나 실행 폴더를 바꾸지 않았다. 산출물과 사내 자료는 Git에서 제외한다.

| 파일 | 크기(바이트) | SHA-256 |
|---|---:|---|
| standalone `BellalunAuto.exe` | 44,026,880 | `f3a417727f8e87589f56806e7c17fbe4b1a9e79629806762d9e043f0973dfbfb` |
| `BellalunAuto-1.0.4-candidate-setup.exe` | 97,344,853 | `c080a8c0187af91bbc209d3d66d2e4ca52f913bca29da42213cb4b7c0076bd9f` |
| `build-info.json` | 170,435 | `a23d3b9e4e9dd9793d695e2faa27698cc5482e54764367e1aaf64b72ef580999` |
| `SHA256SUMS.txt` | 189 | `eba436da057bdb61d2ec2900139574fd3d4cc1e3257e9c64dde2a144828f4d81` |
| `게이트-미통과-후보.txt` | 286 | `00d30a203b5c7fd44ca0b69334defaa309b66ecf63a8a5ea73d59935119b1d03` |
| `BellalunAuto-1.0.4-release.zip` | 96,864,390 | `828cb9d82779fe02a9e7a4284295949e1889369c36bed354dc652629863ee9f6` |

`SHA256SUMS.txt`는 Setup과 외부 build-info 두 파일을 검사한다. ZIP 해시는 위 표에서 별도로 확인한다. ZIP 내부 manifest는 Setup·build-info·후보 표식·사용 안내 네 파일을 검사한다. ZIP은 포터블 실행판이 아니다.

### 확인한 범위

- build-info 등재1,010개 파일의 목록·크기·SHA-256 전수 대조, 추가/누락0이다. 별도 build-info.json1개를 포함한 배포 폴더는 총1,011개 파일이며 내부/외부 build-info 바이트 일치, Setup/build-info 체크섬 일치다.
- 새 standalone EXE를 절대 경로·별도 CWD에서 실행했다. `--version`은 `BellalunAuto 1.0.4`, `--help`는 예상 옵션·명령 안내를 출력했다. 각각 종료0·stderr 없음이며 제품 UI를 열지 않았다.
- ZIP 생성 뒤 최종 위치에서 CRC5개·내부 해시4개를 재검사했다. 원본 Setup·build-info·후보 표식과도 일치한다.
- 인계 사전 해시의 기존1.0.3 설치 EXE/build-info와 Setup/ZIP 네 파일은 그대로다. 기존 설치 파일1,010개도 build-info와 일치한다. 설정과1.0.3 배포 폴더까지 포함한1,018개 파일은 인수 전후 크기·해시가 같다. 설치판은1.0.3·소스d0d3101이다.
- 이번 로컬 전체 단위시험은906 passed / 0 skipped / 293 subtests(49.88초), 정적7종·추적성50 TC 위반0이다. 빌더 안의 시험도906 passed / 293 subtests(36.55초)였다. 검증 스크립트의 독립 검토에서 Critical/Important 지적은 없었다.

### 최종 로컬 게이트

- `node C:/자동화/tools/cleanup-workspace.js --completed <auto> --apply --auto`: 문서64개 검사, 삭제 대상/삭제/실패0이다.
- `node .project-check/project-readiness.js .`: 프로젝트1개·요구사항58개 검사, failed=0이다. SPEC 미결 질문·쉬운 문장 경고2건은 남아 있다.
- `node C:/자동화/tools/check-workspace.js --project <auto>`: failed=0, gateFailures=0, checkerError=false다. verify 미설정·생성물·과거 문서 중복 후보 경고를 확인했으며 전체 단위시험은 별도로 직접 실행했다.
- SPEC HTML과 비공개 상세 HTML을 재생성했다. `tools/check_docs_sync.py`와 `git diff --check`를 확인했다. 비공개 상세 원본/HTML은 저장소 밖에 보존한다.
- 최종 문서 독립 검토에서 Critical/Important 지적은 없다. 목록1,010개와 별도 metadata1개를 구분하도록 사소한 표기 의견을 반영했다.

로컬 기록은 `work/run546-build/status.json`, `work/release-1.0.4-run546/compile.log`·`installer.log`, `work/terminal-build-1.0.4-20261110/verification.json`·`final-artifacts.json`·CLI 로그·`existing-preservation-before.json`·`existing-preservation-after.json`이다. 해당 기록·인계문·설정·산출물은 공개 Git에 넣지 않는다.

빌드 검증을 마친 당시에는 설치 업데이트·설치 후 파일 대조·제품 UI·DB 복원·DICOM·USB·다른PC 시험을 수행하지 않았다. 이후 승인된 설치와 제품 시험은 아래 결과를 따른다. XIPL05의 실제 실패 원인 해소도 미확정이다. 빌드·CLI 검증 결과를 설치·제품 회귀 통과로 사용하지 않는다.

## 승인 후 실행한 UI 범위

사용자가 같은 후보의 설치 업데이트와 기본27 TC·실시간WU13 TC 각1회를 승인했다. 화면·마우스·키보드를 사용하고 승인 Baseline4종 복원·제품 설정·시험 DICOM·기존 시험 USB D:/BellalunWU09 Export/Import를 포함해 로컬에서 수행했다. 추가 재실행·새 빌드·기준 완화는 하지 않았다.

목표는 기본 PASS23/기존FAIL2/MANUAL1/SKIP1, WU PASS10/SKIP3이며 새 FAIL/BLOCKED0이다. 원본 FAIL은 보존한다. 이 문서나 코드 시험 결과가 UI 실행 승인을 대신하지 않는다.


## 2026-11-10 설치판 전체 실측 결과

Setup 종료0·자동 준비 성공 후 설치 파일1,010개 크기/해시와 EXE/build-info 신원을 대조했다. 기존1.0.3 파일이 당시 목록과 일치함을 확인한 뒤 업데이트했으며, 기존 작업622개는 설치 직후 누락0·변경0이었다. 현재 설치판은1.0.4·9847708·dirty=false이며 EXE 해시는 위 산출물 표와 같다.

| 범위 | 실행(KST) | 시간 | 판정 | 제품 종료 |
|---|---|---:|---|---:|
| 기본27 TC | 09:47:33~11:49:06 | 121.6분 | PASS19 / FAIL6 / MANUAL1 / SKIP1 | 1 |
| 실시간WU13 TC | 11:49:26~13:33:33 | 104.1분 | PASS9 / FAIL1 / SKIP3 | 1 |

벽시계3시간46분이다. 기본 실행번호는20261110-094733-91ca29ce, WU는20261110-114926-5c75375b다. 두 신규 보고서는 source_commit=98477088cafb9ad4e1cfcfeee955bd934cf1227e·source_dirty=false·출처build-info다. WU는live/chain_completed=true이며 wrapper 종료0은 기록 수집 완료를 뜻한다.

### 실패와 확인 범위

| 대상 | 실제 결과·남은 범위 |
|---|---|
| 기본WF03/08·WU08 | Patient ID OCR 선택이capture-failed로중단됐다. 기본WF03 selection.json은 목표문구 점수1.0·후보19 capture_errors RuntimeError를 기록했다. 잘린 후보를 제외하거나 임계값을 낮추지 않았다. 후속 Print Overlay/서버/필름 검증의 미수행 Step은 제품 결함과 구분한다. 실제 캡처 실패 원인은 미확정이다. |
| 기본WF05 | Storage SCP 수신 객체0건으로중단됐다. 전송·수신·환경 원인 분리는 미확정이다. |
| 기본XIPL02 | 원본과 변경 Preview의mean_delta/changed_ratio가0이며 Apply 표시만 확인돼 Step7이FAIL했다. 제품·자동화 원인은 미확정이다. |
| 기본WF14·XIPL03 | UPS 복원 차이와Step9 파라미터 유지의 기존FAIL은 보존됐다. 게이트의 기존 허용 목록만 적용했다. |
| XIPL05/07·WU05 | 이번 실행에서는PASS다. 이전 실패 원인의 영구 해소나 재발 방지를 확정하지 않는다. |
| WU09 | USB Export와Import 되읽기PASS다. CD는 기존 수동 범위SKIP이며 USB 통과와 구분한다. 이전 Export.Manager 충돌 원인 해소는 미확정이다. |

기본 Install01은MANUAL, WF16은SKIP, WU01/12/13은SKIP이다. 게이트26개 중24통과·2거부이며 기본 허용 목록 밖FAIL24 check(중단 뒤 미수행 채움 포함)와WU PASS10 목표미달로 거부됐다. 이24개를 독립 제품 결함24건으로 보지 않는다. Setup·build-info·ZIP과후보 표식은 보존하며 정식 배포로 변경하지 않는다.

### 자료 보존과 기록

사전 작업622개 복사본과 기본443개·WU403개 스냅샷을 전수 재해시해 불일치0을 확인했다. config는 보존됐다. 실제 작업 경로의 옛Export DICOM3개는 시험 후 없어졌지만 사전 복사본에 모두 있고123개는갱신됐다. 원래 작업 경로의 모든 파일이 그대로였다고 보고하지 않는다. 기존1.0.3 Setup/ZIP과새1.0.4 배포물도 이전 해시와 같다. 설치 파일1,010개는 시험 종료 후에도 일치했다.

로컬 기록은 `work/installed-1.0.4-full-20261110/`의 `setup.log`, `install-before.json`, `install-after.json`, `preservation-before.json`, `preservation-install.json`, `before-workspace/`, `suites/verification.json`, `suites/snapshots/`, `release-gate.json`, `final-verification.json`이다. 설정·DICOM·증거·사내 패키지는 공개 Git에 넣지 않는다. 다른PC/OS·사람 검수·브라우저 육안 검수는 이번 수행에 포함하지 않았다. 추가 수정과 새 UI 재실행은 수행하지 않았다.

최종 문서 검토의 낡은 미승인 문구를 빌드 당시 이력으로 바로잡았고 추가 Critical/Important 지적은 없다. 정리 도구는64문서 검사·삭제0, readiness failed0(기존SPEC 경고2), workspace failed0/gateFailures0, 문서 동기화·diff 검사 통과다. workspace의 verify 미설정 경고는 남아 있으며 이번 제품 두 전체 결과와 게이트 거부를 별도로 직접 확인했다. 정상 기존OCR5.4는 유지됐고 설치 준비의 기준5.5.3 차이WARN도 보존했다.


## 2026-11-10 추가 FAIL 원인 조사와 개선안

사용자가 기억한 정상 실행을 보존 보고서로 확인했다. 후보11과11월6일 후보9의 기본기능은PASS23·기존FAIL2였다. 최신 빌드의 추가FAIL을 기존 정상 동작과 비교했으며 제품·UI·DB·설정·전송을 새로 조작하지 않았다. 제품 소스는 수정하지 않았다.

### 정상 실행부터의 변화

아래 각 묶음은 verification.json의 report_sha256과 스냅샷 보고서 해시를 대조했다. 비교8개 보고서는 `work/investigation104/comparison.json`에 기록했다.

| 실행 | 기본기능 FAIL | WU FAIL |
|---|---|---|
| 후보11 | 기존WF14 UPS·XIPL03 | 없음 |
| 후보9(44052ec) | 기존WF14 UPS·XIPL03 | WU09 USB Export 충돌 |
| 1.0.3(d0d3101) | 기존2개 + WF03/08·XIPL05/07, WF14 목록 실패 추가 | WU05/08/09/11 |
| 1.0.4(9847708) | 기존2개 + WF03/05/08·XIPL02 | WU08 |

1.0.3과1.0.4의 기본FAIL6은 같은 실패6개가 아니다. XIPL05/07과WF14 목록은이번에통과했고WF05·XIPL02가새로실패했다. 추가4 TC와WU08은 세 조사 주제(OCR·수신관측·Preview 준비)로 묶인다. 제품 신규 결함4건으로 확정하지 않는다.

### 1. OCR: 회귀 시점과 실패 지점 확인

정상 코드56a0bc6/44052ec는 최고점수 후보를 골랐다. d0d3101은 미판독 경쟁 후보가 있으면 선택을 거부하도록 바뀌었다. run542의 후보19는 Study Date 행 하반부가잘려 unreadable이었다. f4887b2에서행노출회복을추가했으나1.0.4는같은후보19에서capture-failed로중단됐다. 목표Patient ID는점수1.0·신뢰도90 이상이다.

네 selection.json과 이전019-raw.png를대조했다. 원본이미지 확인범위는이전잘린행과이번XIPL이미지다. 1.0.4 후보19 원본PNG는생성되지않았다. `core/ocr_selection.py:180`은예외타입RuntimeError만남겨정확한실패원문을복원할수없다. `core/print_overlay.py:293`의행신원소실·`:302`의노출실패·`core/ui.py:719`의전면클릭차단을현재증거로구분할수없다.

**확정 개선점:** 경쟁 후보 판독 정책을 유지하면서 실제20행·마지막부분노출에서 회복되는 선택기를 만들어야 한다. 스크롤 후 위치 변화와컨트롤을다시조회하고, 실패단계·정제한예외원문·전후행기하·신원·전체목록캡처를보존한다. HWND가재생성되는지는실측후논리항목재식별에반영한다. 후보19제외·임계값완화·무조건최고점수선택으로되돌리지않는다.

현재시험은2개행과클릭즉시10px움직이는모의다(`tests/test_print_overlay_selection.py:62`). 20행·지연이동·무효스크롤·행재생성·같은문구경쟁·선택직전재노출의회복시험이필요하다. 실제reveal함수의오프라인모의에서무변화50클릭후노출실패, 행소실시신원실패를재현했다. 실제발생갈래의확정은아니다.

### 2. WF05: 전송 기록과 수신 관측을 분리해야 함

제품Viewer로그의10:13:58.612~10:14:23.347에는Queue14/15/16의등록·C-STORE요청/응답·Done이있다. 보고서는14/15만수집했다. `core/send_verify.py:327`은첫비어있지않은목록에서즉시반환하며`:357`은그때고정한Key만기다린다. 실제함수에[14,15]뒤[14,15,16]을주는모의에서조회1회로16누락을재현했다. **Queue 전체 수집 결함은 확정이다.**

하지만Queue누락이최종수신0건의직접원인인지는미확정이다. `core/send_verify.py:53`은HTTP·ZIP·파싱예외를None으로숨기고`:219`는빈목록으로바꾼다. 현재StudyUID필터후0건과실제조회실패가같은수신0건으로표시된다. 실제received함수에가짜API예외를넣어None반환·caller의빈목록변환을오프라인재현했다.

당시API응답·ZIP·예외원문·서버저장로그가보존되지않아정확한수신0건원인은복원불가다. 세전송객체의식별태그는후속PASS한WF06전송과같았으며현재서버조회로당시수신성공을소급확정하지않았다. 이경로의코드는d0d3101→9847708사이에변경되지않았다.

**확정 개선점:** 이번전송의원본객체·Queue등록수렴·전체Queue완료를연결해후발등록을포함한다. 정상조회0건, HTTP실패, ZIP실패, DICOM파싱실패, 현재Study불일치를구분하고시각·응답해시·정제오류·ZIP해시/객체수·필터전후수를남긴다. 공유서버전체삭제와과거UID혼합은해결책으로쓰지않는다. 수신태그대조기준은유지한다.

### 3. XIPL02: 완료 대기와 활성 판정의 구현 공백

같은1.0.4기본/WU의selected.png는SHA-256이같다. 기본preview는처리ROI변화0, WU는mean1.621·ratio0.025302다. 원본두preview PNG를직접열면기본Apply/Cancel은회색, WU는활성색이다. 당시Win32 enabled값은기록되지않았다. 기본RGB차이영역은우측컨트롤뿐이며ROI가영상을놓친상태는아니다.

`tests/xipl_flows.py:207`은파라미터로그만으로완료를선언하고`:534`에서즉시캡처한다. `:540`은Apply visible만검사하지만Expected는활성이다. **활성 기대값을가시성으로검사하는구현공백은확정이다.** 실제predicate는화면상태입력없이파라미터로그만주면완료를반환하는것도오프라인재현했다.

기본완료대기는1.149초, 파일mtime기준PNG저장시각은로그완료감지약89ms후다. mtime은정확한촬영시각과구분한다. 정상1.0.3은1.591초이며후보11/후보9/이번WU의변화율은약0.0253이다. 조기판독경쟁조건이유력하다. 다만후속프레임이없어더기다리면정상인지처리가정지했는지확정할수없다. 2D처리대기로직은두최근소스사이에변경되지않았다.

**확정 개선점:** 파라미터로그와실제버튼enabled·처리완료신호·화면안정을함께기다린뒤판정한다. 처리미완료timeout과완료후실제영상변화0을분리한다. 로그선행/렌더지연, 영구비활성, 활성후실제0변화를각각시험한다. 변화율0.005기준은유지하고고정sleep증가로대체하지않는다.

### 구현·검증의 통과 기준

| 우선 작업 | 수정 대상 | 회귀시험에서 입증할 것 |
|---|---|---|
| 1. 원인 증거와 오류 구분 | ocr_selection, send_verify, storagescp | 서로다른스크롤/API/ZIP/파싱실패가구분되고정제한예외원문이보존됨. 조회실패가정상0건으로표시되지않음 |
| 2. OCR 실제 상태 회복 | print_overlay와관련선택시험 | 실제20행기하에서마지막행완전판독, 지연/무효이동/재생성처리, 경쟁문구거부와선택직전유일성유지 |
| 3. 전송 전체 수렴 | send_verify와전송시험 | 후발Queue16을누락하지않고등록집합수렴·전체Done·이번Study실제수신/태그를연결함 |
| 4. Preview 준비 대기 | xipl_flows와UI상태조회 | 로그만도착한상태는완료가아님. 실제enabled/완료/화면안정후기존픽셀기준으로판정함 |

각결함은기존구현에서실패하는재현시험을먼저만든뒤수정한다. 임시모의로성공만주는시험을반복하지않고이번기하·화면·시간순서를포함한다. 수정후소스검증과독립검토를마친후후보를한번만빌드한다. 그후같은후보로OCR목록선택·WF05전송·XIPL02 Preview/Apply를집중확인하고, 집중검증을통과한후공용영향범위의전체회귀를1회수행하는순서가적절하다. 추가제품조작·DB복원·새빌드의UI회귀는승인후수행하며이번조사에서는실행하지않았다.

오프라인근거는 `work/investigation104/comparison.json`, `agent-findings.md`, `replay-results.json`, `compare_reports.py`, `replay_evidence.py`다. 부모가주요코드·제품로그사건·기본/WU원본이미지·픽셀통계와모의재현을재확인했다. 확인된자동화결함과실제실행에서아직분리되지않은최하위원인은위와같이구분한다.

조사문서독립검토의추가Critical/Important지적은없다. 비교보고서8개재해시불일치0, 정리65문서·삭제0, readiness/workspace 실패0을확인했다(기존경고유지). 이번검증은저장증거·실제함수오프라인재현·문서검사이며제품재시험통과를뜻하지않는다.

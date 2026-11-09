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

기존1.0.3 설치판·Setup·ZIP·원본 보고서·증거는 그대로 보존한다. 해당 실제 전체 실행과 거부된 배포 게이트는 [과거 검증](ocr-release-validation.md)을 따른다. 새 후보의 UI 실행은 아직 승인받지 않았으며 배포 PASS가 아니다.

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

설치 업데이트, Setup 내부 파일의 설치 후 대조, 제품 UI·DB 복원·DICOM·USB·다른PC 시험은 미수행이다. XIPL05의 실제 실패 원인 해소도 미확정이다. 빌드·CLI 검증 결과를 설치·제품 회귀 통과로 사용하지 않는다.

## 승인받을 UI 범위

공용 OCR·UI 선택·대기·WF14 목록 수집 변경이 기본기능과 WU 모두에 영향을 주므로 qa-test-02에서 같은 새 후보 EXE로 기본27 TC와 실시간 WU13 TC를 각각1회 제안한다. 예상4~4.5시간, 화면·마우스·키보드를 점유한다. 승인 Baseline4종 복원·제품 설정·시험 DICOM·기존 시험 USB D:\BellalunWU09 Export/Import가 포함된다. 실제 장치·경로·desktop 예약과 설치 신원을 확인한 후 실행한다.

목표는 기본 PASS23/기존FAIL2/MANUAL1/SKIP1, WU PASS10/SKIP3이며 새 FAIL/BLOCKED0이다. 원본 FAIL은 보존한다. 이 문서나 코드 시험 결과가 UI 실행 승인을 대신하지 않는다.

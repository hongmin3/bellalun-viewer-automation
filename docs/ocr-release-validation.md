# 1.0.3 OCR 개선 검증

## 소스와 오프라인 판독

2026-11-09 소스 시험882 passed / 3 skipped / 293 subtests. 정적 검사·SPEC readiness 통과.
별도 worktree에서 원본 사양/체크리스트 위치를 지정한 추적성 검사 TC50건·위반0이다.
실제 설치된 Tesseract로 일반/역상 라벨8개·중복 후보1개·짧은근사 거부1개를 비교해10개 기대 결과가 일치했다.
합성 이미지 결과는 다른 PC의 당시 실패나 제품 UI 통과 근거가 아니다.

독립 검토에서 WF03의 증거 경로 초기화 전 사용, 저신뢰 경쟁 후보를 무시한 선택,
기본 엔진의 실패 지문 누락과 캡처 실패 분류를 발견했다. 해당 경로를 실패 시험으로 재현하고 수정했다.

## 빌드·설치·제품 검증

소스 `d0d310133bf71fcfd68f566457fcf44bd9ab3bf1`, dirty=false의1.0.3을 컴파일·시험 생략 없이 빌드했다.
빌드 환경 시험도882 passed / 3 skipped / 293 subtests다. Setup 종료0, 자동 준비 성공,
설치 파일1,010개 SHA-256 대조 불일치0을 확인했다. 기존 작업401개는 누락0이며,
변경된 기존 파일은 설치 준비 요약 `install-preparation.txt` 하나다. 기존 config는 보존됐다.

| 산출물 | SHA-256 |
|---|---|
| EXE | `165e979d420ec9b392262226789fe424fa01ee4e0f72a24c5712fd6475019090` |
| Setup | `5be2135f02efd3d64fb46a58ceb93e25cbd6413ef576cd241aabb38f250f998e` |
| 릴리즈 ZIP | `8e9fdde573f6ecef822f55ffd7e221e41564a07816c113e0f8ccd991e2a2e74f` |

파일은 Git 제외 `release/1.0.3/`에 있다. `BellalunAuto-1.0.3-release.zip`은92.4 MiB이며
Setup·build-info·후보 표식·사용 안내·내부 체크섬을 포함한다. ZIP CRC 정상·내부4개 파일 해시 일치를 다시 확인했다.
사내 자료를 포함하므로 공개 Release에 올리지 않는다.

새 설치 EXE의 격리 첫 실행에서 준비 점검 창을 실제로 열었다. OCR5.4.0/기준5.5.3 차이,
엔진·언어 해시, 합성 캡처에서 생성한 HVL 중복 후보의 재판독4회·실패 안내·증거 열기 버튼 표시를 확인했다.
이 합성 실패는 별도 시험 작업 폴더에만 두었으며 실제 제품 실패 이력으로 사용하지 않는다.
이 초기 확인에서는 클릭 후 선택 변화를 확인하지 못했다. 후속 run542/543의 실제 화면 확인 결과는 아래에 구분한다.

제품 UI 회귀는 run542에서 같은 설치 EXE로 두 묶음을 각각 1회 종료했다. 기본기능은 PASS 19 / FAIL 6 / MANUAL 1 / SKIP 1, 실시간 WU는 PASS 6 / FAIL 4 / SKIP 3이며 배포 게이트는 거부다. run541은 메모리 부족으로 시작 전에 멈췄고, 직접 앱 정리 요청 후 run542에서 진행했다. 개별 TC의 중단 뒤 채워진 미수행 Step을 실제 수행으로 세지 않는다.
다른 PC·OS 실측도 미수행이다. 후보 표식을 보존하며 과거1.0.2/1.0.1의 성공을1.0.3 검증으로 사용하지 않는다.
로컬 상세 근거는 `work/ocr-release-verification-d0d3101.json`과 `work/gui-exe-1.0.3-new/diagnostics-proof.png`다.

## 2026-11-09 설치판 전체 검증 시작 전 차단 (run 541)

- Worker 설정과 Hub 배정·desktop 예약은 `qa-test-02`/run541에 일치한다. Windows 호스트명은 별도 식별자다.
- 시작 시 소스 HEAD는435a374이며 원격 main과 차이0이었다. 기존 `docs/SPEC.html`은 줄끝 정규화 후 HEAD와 같음을 확인하고 원본 바이트를 로컬 보존한 뒤 이번 CHANGELOG에 맞춰 생성 도구로 갱신했다.
- 설치 파일1,010개 크기·SHA-256 일치, 위 EXE·Setup·ZIP 해시 일치, build-info의 소스·dirty=false·compile/tests 생략false를 재확인했다. 새 빌드·재설치는 하지 않았다.
- 기존 격리 미리보기에서 OCR 지문 WARN과 원인·다음 행동, 합성 HVL 중복/재판독4회 안내는 보였다. 마우스·키보드 입력 후 행 선택 변화는 확인하지 못했다. 증거 폴더 열기·다시 점검·정상 화면 복귀는 미검증이다.
- 해당 미리보기의 설치 EXE 경로·격리 작업 폴더·자식 프로세스 없음 확인 후 그 프로세스만 종료했다. 다른 사용자 창·Worker·제품 서비스는 종료하지 않았다.
- 미리보기 종료 직후 가용 물리 메모리는803.9 MiB였다. 중간 측정은 WARN 경계까지 회복했지만 전후 여러 번1 GiB 미만이었다. `core/env_preflight.py`의 기존 차단 기준을 완화하거나 다른 작업을 종료하지 않았다.
- 기본27 TC/WU13 TC 모두 미수행이며 새 제품 리포트·실행 후 스냅샷·배포 게이트 판정은 없다. DB 복원·제품 설정 변경·DICOM 전송·USB 쓰기도 시작하지 않았다. WF03/08의 실제 OCR 경로·다른 PC/OS는 미검증이다.
- 당시 재개 조건은 메모리 확보였다. 이후 사용자가 AI의 직접 앱 정리를 요청해 run542에서 차단 기준을 넘긴 뒤 같은 승인 범위로 실행했다.
- 로컬 사전 점검 기록: `work/installed-1.0.3-preflight-run541/preflight.json`. 제품 시험용 `verification.json`이나 PASS 기록으로 사용하지 않는다.

## 2026-11-09~10 설치판 전체 실행 결과 (run 542, 후속 확인543)

창 없는 Edge와 이번 실행이 띄운 미사용 도구만 정리했다. 다른 프로젝트 프로세스·Worker·제품 서비스와 OCR/언어 파일·설정은 변경하지 않았다. 실행 직전 가용 메모리는1,173.3 MiB로1 GiB 차단 기준 이상이며2 GiB 권장 기준 미만 WARN이다. 실제 환경 점검은blocked=false이며 해상도·DPI·USB·재부팅 대기·시계·검증 환경 대조는OK다. 메모리와 작업표시줄 자동 숨김은 비차단WARN을 유지한다.

### 실행 신원과 시간

Worker는 qa-test-02다. 위 1.0.3 EXE·Setup·ZIP 해시, build-info 소스 d0d3101·dirty=false·compile/tests 생략 false와 설치 파일 1,010개를 실행 뒤 다시 대조했다. 모두 일치한다. 소스나 실행 파일을 고쳐서 재실행하지 않았다.

| 명령 | 시작~종료(KST) | 래퍼 실측 | TC 판정 |
|---|---|---:|---|
| run-regression | 11-09 21:06:10~23:05:26 | 119.3분 | PASS 19 / FAIL 6 / MANUAL 1 / SKIP 1 (27행) |
| run-winupdate | 11-09 23:05:34~11-10 00:43:38 | 98.1분 | PASS 6 / FAIL 4 / SKIP 3 (13행) |

두 명령의 벽시계 구간은 217분 28초다. WU는 live·chain_completed=true다. 양쪽 제품 종료 코드는 1이며, 래퍼의 완료 기록은 제품 PASS를 뜻하지 않는다. HTML은 엔진 구간을 사용해 기본 119.2분·WU 97.9분을 표시한다. 과거처럼 집계 객체 시간만을 전체 소요로 표시하지 않는다.

### 실패와 미수행

| 범위 | 관찰과 한계 |
|---|---|
| WF03·WF08, WU08 | Patient ID 선택에서 SelectionError(unreadable). 관련 OCR 기록 4개 모두 4회 재판독·최고점수 1.0이며 대상 문구는 정확히 읽혔다(최초 신뢰도 95.114738). 다른 후보 19번 영역의 잘린 행 때문에 전체 후보 판정이 거부됐다. 저장된 reads를 같은 rank에 넣어 동일 거부를 확인했다. OCR 엔진 실행 오류나 제품 결함으로 단정하지 않는다. |
| WF14·WU11 | 기존 UPS 미복원 외에 dicom.print_overlay의 목록 행 열거 불완전이 발생했다. 따라서 기존 UPS 허용만으로 통과시킬 수 없다. |
| XIPL03 | 기본기능 Step9의 기존 파라미터 유지 실패는 원본 FAIL을 보존하고 기존 허용 목록으로만 분류했다. |
| XIPL05·XIPL07, WU05 | 3D-wide F8 후 파라미터 적용 로그 미확인, Post Reconstruction 창 미표시로 중단됐다. WU05의 창 미표시는 기존 Step9 유지 결함과 다른 실패다. 제품·자동화·환경 원인 분리는 추가 조사가 필요하다. |
| WU09 | Patient ID 검색 옵션을 찾지 못해 중단됐다. USB Export/Import 완료를 확인하지 못했다. 이전 Export.Manager 충돌의 재현·해소 근거로 사용하지 않는다. |

WF03/08의 Print Overlay 카탈로그·이름·Header 콤보·Print 서버 선택, DB FieldID·Position·Header 저장값과 Film Header/Top/Bottom 실제 표시는 미수행이다. 임의 DB DELETE·순번 선택·기대값이나 임계값 완화로 진행하지 않았다. 기본 Install01은 MANUAL, WF16은 사람 전용 SKIP, WU01·12·13은 사람 전용 SKIP이다. TC 행과 체인이 끝났어도 중단 뒤 미수행 Step은 별도로 남는다.

### GUI와HTML 실측

일반 권한 GUI에서 준비 점검 진입, 다른 행에서 OCR WARN으로 선택 변화와 원인/다음 행동, 다시 점검 후 결과 재표시, 닫기 후 정상 화면 복귀를 확인했다. 관리자 권한 창의 입력 미반영은 이 확인과 구분하며 제품 시험은 기존 관리자 경로를 사용했다.

run543에서 `work/gui-1.0.3-synthetic-run543/`에 기존 HVL 후보 중복 합성 사례만 복사하고 SYNTHETIC-ONLY 표식을 뒀다. 최근 실패 행 선택 후 안내 변화, 증거 폴더 열기 버튼으로 탐색기에 11개 파일(원본/전처리 크롭·selection.json)이 실제로 열림, 정상 화면 복귀를 확인했다. 기존 보호된 격리 증거는 일반 권한 GUI에서 열거되지 않아 원본 권한을 바꾸지 않고 별도 시험 폴더를 사용했다. 합성 사례의 GUI 통과는 실제 제품 OCR 통과가 아니다.

Chrome 실제 창에서 원본과 해시가 같은 보존 HTML 두 개를 열었다. 요약·엔진 실행 시간·실패/수동 카드를 시각 확인했고, FAIL 필터 6/4행·TC 검색 각 1행·빈 검색 0행·초기화 27/13행을 확인했다. 링크 220/43개(고유 130/22개)의 대상 누락 0·페이지 오류 0이다. 브라우저 기록은 `browser-verification.json`과 `browser-run-regression.png`, `browser-run-winupdate.png`다.

### 보존과 배포 판정

기존 작업 402개 240,050,231바이트의 사전 복사본을 실행 뒤 다시 해시 검사해 불일치 0을 확인했다. config도 유지됐다. 실제 작업 경로에서는 시험으로 134개가 갱신됐고 옛 Export DICOM 3개는 없어졌으나 그 원본은 사전 복사본에 모두 보존돼 있다. 원본 경로가 모두 그대로였다고 표시하지 않는다.

명령 직후 보존한 스냅샷은 기본 351개·WU 307개이며 재해시 불일치 0이다. WF08의 기본 작업 폴더 밖 OCR 증거 2폴더 202파일도 추가 복사·해시 대조했다. 원본/전처리 크롭·판독문·점수·신뢰도·영역·엔진/eng 지문을 보존했다. 기존 정상 OCR 5.4.0과 설정을 교체하지 않았다.

`tools/release_gate.py --installed-verification work/installed-1.0.3-full-run542/suites/verification.json --scope both --commit d0d310133bf71fcfd68f566457fcf44bd9ab3bf1 --output work/installed-1.0.3-full-run542/release-gate.json` 결과는 26검사 중 24통과·2거부다. 기본 허용 목록 밖 FAIL 23개 check(미수행 채움 포함)와 WU 목표 미달로 거부됐다. 이 23개는 독립 제품 결함 23건이라는 뜻이 아니다.

후보 파일명·build-info·ZIP의 제작 당시 미검증 안내를 보존한다. 현재 별도 배포 판정도 거부이며 정식 PASS로 바꾸지 않는다. 추가 수정·새 빌드·UI 재실행·DB 복원은 이번 실행 승인에 포함하지 않는다.

상세 기록은 Git 제외 `work/installed-1.0.3-full-run542/`에 있다: `suites/verification.json`, `release-gate.json`, `preservation-after.json`, `gui-verification.json`, `browser-verification.json`, `final-verification.json`, `suites/snapshots/`, `external-ocr/`, `before-workspace/`. 사내 ZIP·원본 로그·환자/DICOM·증거는 공개 저장소나 Release에 올리지 않는다. 다른 PC/OS 실측은 미수행이다.

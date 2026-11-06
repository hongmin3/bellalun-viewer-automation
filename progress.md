# 진행 상태

## 2026-11-06 설치 구성품 자동 준비 완료

- VXvue 설치 후 준비 명령을 참고해 OCR 오프라인 설치, Baseline4종과 자료 해시 검증, 기존 설정 보존·신규 설정 연결, 완료 요약과 실패 종료 코드3을 구현했다. 제품 Server·SQL·XIPL 설치나 DB 복원은 실행하지 않는다.
- 공식 Tesseract5.5.3 release digest와26,573,224바이트 설치 파일 SHA-256을 대조했다. 기존 OCR5.4는 정상 재사용한다. 새 PC 누락 경로는 격리 시험이며 실제 clean PC 설치는 미검증이다.
- 코드 검토의 기존 OCR 설정 불일치·PATH 작업 폴더 후보 실행 문제를 실패 시험 후 수정했다. 소스820 passed/4 skipped/267 subtests, 정적7종·readiness·workspace 검사 통과.
- 소스5004de0·dirty=false의1.0.2 후보를 생략 없이 빌드했다. 새 EXE의 신규 설정0·기존 설정0·잘못된 OCR 설정1과 설정 보존을 확인했다. 실제 업데이트는 Setup0·자동 준비0, 파일1,010개 해시 일치·기존 작업381개 보존·준비 요약1개 추가다.
- 전달 파일은 `release/1.0.2/BellalunAuto-1.0.2-candidate-setup.exe`. 상세와 해시는 `docs/setup-preparation-validation.md`. 실제 다른PC 누락OCR 설치·완료 화면 육안 검수·새 EXE 제품 전체 회귀는 미검증이다. 기존173eb3c WU 통과는 해당 EXE에 한정한다.
- 후속 요청으로 최종 파일5개를 `release/1.0.2/`로 옮기고 향후 빌드도 버전별 폴더에 모으도록 바꿨다. 이동 후 해시3개 일치, 구버전 폴더18개·9.67GiB 제거, 구버전 Setup/ZIP 잔존0이다. 메타데이터·로그·실행 증거는 `work/release-build-records/`에 보존했다. 최신 소스 시험821 passed/4 skipped/267 subtests다.

## 2026-11-06 설치판 WU 전체 완료

- 사용자 승인에 따라 WU만 실행했다. 소스173eb3c·dirty=false 기존 빌드를 재사용해 설치판 업데이트·자료364개 보존·실행파일1007개 대조를 확인했다. 해당 WU 실행을 준비하던 시점의 코드 차이는 문서뿐이었다.
- 실행11:05:28~12:54:47,109.3분, 제품 종료0. live/chain_completed=true, PASS10/SKIP3(사람 수행 WU_01·12·13)/FAIL0. WU 범위 게이트14개 통과, 보존 스냅샷246개 해시 불일치0.
- 이번 WU_09 USB Export/Import와 WU_10은 PASS. 기존 Export 충돌의 원인 수정·재발 해소를 확정하지 않는다. 원본 WF14 UPS·XIPL03 Step9 FAIL은 그대로 보존돼 있다.
- Chrome 실제 결과 페이지의 요약·펼치기·링크23개를 확인했다(누락/페이지 오류0). 화면의 총 소요9.4분은 전체109.3분과 달라 보고서 시간 표시 문제로 남겼다.
- 기본기능 전체의 새 실행은 보류한다. 당시 설치 신원·범위·미완료는 `docs/wu-installed-validation.md`. WU 실제 전체 실행 시간 표시와 WF14 계측 밖 비용 세분화는 남아 있다.

## 2026-11-06 WF14 단독 검증 완료·전체 회귀 보류

- 소스173eb3c·dirty=false를 컴파일/시험 생략 없이 빌드했다(빌드 환경805 passed/4 skipped/265 subtests). 별도 배포 폴더 EXE로 단독 실행했고 설치판 업데이트·DB 복원·USB 시험은 하지 않았다.
- 화면 가림으로 중단된 첫 실행은 사용자 요청으로 제외·보존했다. 재실행10:09:07~10:40:51, 31분44초. PASS20/FAIL3(UPS 차이와 연쇄 중단), 목록89행·849항목 복원과 설정7개 정리는 PASS. 파일1007개·실행 보존본126개 해시 불일치0.
- 4구간 계측 완료: 페이지 합계5분4초, 목록11분41초, 나머지 준비·변경·전송·재시작·정리14분59초. 후보9보다57초 짧지만 시작 상태가 달라 성능 개선 확정 근거로 쓰지 않는다.
- Edge·Chrome 실제 HTML에서 시간표·항목별 펼치기·링크25개를 각각 검사했다(누락/페이지 오류0, 가로 넘침 없음). Chrome은 공식 Google MSI 설치 후157.0.8103.39를 확인했다. 상세는 `docs/wf14-single-validation.md`.
- 사양 원본486~487쪽에서 과거 UPS 제외 문구의 취소선을 확인했다. 텍스트 추출의 제외 문구를 현행 사양으로 간주했던 가능성 언급을 정정한다. UPS 판정 제외는 적용하지 않는다.
- 전체 회귀는 사용자 요청으로 보류한다. 다음은 계측 밖15분 및 목록 내부 시간 세분화다. 현재 판정·게이트는 유지한다.

## UI 제어 없는 개선 (2026-11-06)

- #86 종료 후 이 세션으로 이관. WF14 수집 4구간 시간·HTML 시간표, 구조화된 JSON 값과 HTML 접기, 설정 레일의 얕은 탐색을 추가했다.
- 당시에는 UI·DB 복원·USB 쓰기·설치 회귀를 제외했다. 이후 승인된 WF14 단독 실행 결과는 위 절을 따른다. 기존 후보9 결과도 보존했다.
- 설정 레일 탐색·WF14 전수 판독과 변경 설정7개 정리를 위 단독 실행으로 확인했다. UPS Import 복원은 FAIL이며 정리 재적용 후 별도 재조회 증거는 없다. 공용 결과 변경 영향의 기본+WU 설치판 전체 회귀는 보류 중이다.
- 남은 설계: 페이지·목록 순회 통합, 상태 기반 행 대기, 통합 배포 대시보드와 WU 원본 단계 시각. UI 상태 신호를 확인하지 못한 최적화는 실제 관찰 후 결정한다.
- 소스 검증: 807 passed / 2 skipped / 265 subtests. 독립 검토에서 WU 저장점 재개 데이터 손실을 발견해 왕복 시험과 복원을 추가했다. 정적7종·readiness·workspace gate 통과(기존 경고 유지).

## 2026-11-06 후보9 두 전체 종료·WU_09 제품 충돌 조사 대기 (Issue #86)

- WF_02 자동화 결함은 실패 시험4건 확인 후 수정했다. 75초 조기 판정과 이전 그룹의 결과를 현재 촬영으로 오판하는 문제를 새 그룹의 Raw/Recon/Syn 도착 대기(기존 공용 상한180초)로 고쳤다. 정확한 건수·3D-N 구조·게이트 유지. 조사 표·시간 분포·최초 Viewer DB timeout 원인의 미확정 범위는 `docs/wf02-acquisition-investigation.md`.
- 소스 검증·독립 검토: 798 passed / 4 skipped / 265 subtests, 정적7종·readiness·workspace gate 통과. `44052ec7d8ccb3cde0e59b769e24f53833207c64`를 main에 push했다. 후보8 단독 진단은 PASS27/FAIL0으로 원래 지연 미재현, SQL 차단0이었다. 최초 실패 때의 SQL 원인을 배제하지 않는다.
- 후보9: 같은 소스·dirty=false, 팀 설정 포함 WMI 빌드 종료0(compile/tests 생략 없음). EXE `0a37093feac4a63dbe55e73b8b755cc880d055f1121badbeccade55926c7d875`, Setup `225082dc32858cc96d66a7eb984e2da4e8179387e181e821c09b4ab1742664d0`, build-info `8da8eb45dbec53b09dfb6cede925679118de8d8ee07028b32b96795bc6eea611`. 후보8 위 무창 업데이트·설치 파일1007개 대조 불일치0. 기존 작업 파일325개(설정 포함) 해시 전부 보존. Users Modify·바로가기2개, Explorer 기동 프로그램 창1개·새 콘솔0·준비23행(22OK+관리자 안내1) 확인.
- 설치판 두 전체1회 완료: 기록 `C:/BellalunAuto 실행 기록/후보9-full-20261106_045123`. 기본 `20261106-045125-a36633b7` 04:51~06:54, 122.9분, 종료1, PASS23/FAIL2/MANUAL1/SKIP1. WF_02 PASS27/FAIL0, 3D-N 대기33.7초·3D-W22.9초 및 후속 Tool·종료 통과. FAIL은 기존 WF_14 UPS 복원·XIPL_03 Step9 제품 결함뿐이다. WU `20261106-065431-58e67b2b` 06:54~08:40, 106.4분, 종료1, PASS9/FAIL1(WU_09)/SKIP3. 체인 끝까지 수행. 각 스냅샷287/244파일 해시 대조 통과. wrapper 종료0은 기록 수집 성공이며 제품 시험 통과가 아니다.
- 새 WU_09 실패: 08:31:38 USB IMG Export 시작 후 08:31:53 `EXPORT.MANAGER.exe 1.0.12.105` 충돌. Windows Event1000(모듈 ntdll.dll, 예외 c0000374)·1001 및 끊긴 제품 로그를 대조했다. IMG3개 존재만으로 성공시키지 않았고 Import는 미수행이다. 자동화는 유일한 Manager 창/완료 문구를 확인하지 못해 FAIL했다. 충돌 유발 원인·빈도는 미확정이며 자동화 결함이라고 단정하지 않는다. 근거 `docs/wu09-export-crash-investigation.md`, 로컬 `work/candidate9-regression/wu09-crash-events.json`.
- 배포 게이트: `work/candidate9-regression/release-gate.json`, 26개 중25개 통과·거부1건(WU_09). 기대값·상한·허용 목록 변경 없음. 배포 통과/완료로 표시하지 않는다.
- 공유 ZIP: 각 실행 직후 보존 스냅샷에서 보고서8개와 PNG117개를 선택했다. 원본 보고서는 보존하고 공유 입력의 링크만 각 스냅샷으로 다시 연결했다. 파일125개 해시·상대링크123개 일치, 설치판 verify-share0·누락/변조/추가 각1. 같은 PC 다른 한글/공백 경로에서 네트워크 차단 검증. DICOM 제외, 로그 선택했으나 참조 로그 없음. 기록 `work/공유 검증/후보9 두 전체 오프라인/verification.json`. 다른PC·브라우저 화면은 미확인.
- 다음: 추가 USB 단독 진단·제품 충돌 조사 범위 승인 대기. 기존 검사·USB 관리 폴더를 사용하고 DB 복원 없이 관찰하는 범위를 우선 제안한다. 추가 UI 실행·새 회귀는 시작/예약하지 않았다. 사람 검수·UAC 취소·다른OS/계정·제거·다른PC는 미완료다.

## 2026-11-05 XIPL 9784 점검 수정·후보8 (Issue #85 이어서)

- 사용자 결정(22:35): "가로 해도 문제가 없다면 가로". 후보7 보고의 (가)를 택했다. gate 조건(XIPL.SERVER 프로세스 + 9784 수신)은 그대로 두고 측정 방법만 바꾼 후보8을 만들어 기본기능·WU 두 전체를 한 번 수행한다. (나)의 PC 드라이버·업데이트 확인은 이번에 하지 않는다.
- 22:3x 재확인: TCP 표 이상 지속. `Get-NetTCPConnection -LocalPort 9784`는 `127.0.0.1:9784`(XIPL.SERVER PID 13988)를 `Closed`로, `-State Listen` 조회는 0건을 준다. `netstat`도 `0.0.0.0:445`를 `FIN_WAIT_1`로 준다. 열거형 밖 값 0 때문에 `State` 접근 자체가 예외를 내는 행도 있다.
- 수정(REQ-QA-005, REQ-REGRESSION-001): `core/preflight.check_xipl`이 상태 값을 읽지 않는다. 원격 포트 0인 9784 소켓이 XIPL.SERVER PID 소유이고 실제 TCP 접속(2초)을 받아야 통과한다. 실패 시험 7건을 먼저 확인했다. 이 PC 실측: 새 점검 `ok=True`, 기존 `-State Listen` 조회 0건.
- 독립 검토: 막는 결함 없음. 첫 수신 행만 접속하던 점(중간)을 모든 소유 수신 소켓 시도로 고치고 시험을 보강했다. 점검 접속이 XIPL에 남기는 영향은 실측으로 확인했다(서버 로그에 `accepted`/`closed client connection` 정상 기록, 11-04 로그상 다중 클라이언트 index 0~2 수용). 남은 이론상 경우: XIPL이 bind만 하고 다른 프로세스가 같은 포트의 특정 주소로 수신하면 통과할 수 있다(가능성 매우 낮음, 미대응).
- 검증: 전체 단위시험 794 passed / 2 skipped / 265 subtests, 정적 7종 이상 없음, readiness 실패 0(기존 경고 2).
- 커밋 `7d5b1fa` push. 후보8: 소스 `7d5b1fa9d75816fe7f7d6112922cd7b6f1059a0f`·dirty=false, 팀 설정 포함 WMI 빌드(PID 5076) 종료 0, 빌드 환경 792 passed / 4 skipped. EXE SHA-256 `B51627CCE41A79D158D5AF87295953D1DC30A1C1444E89849F86DC621BEFD7F1`, Setup `07E6897BC21277F9AD4BEAC72FCF79C3719DD4F14327B49184E761847A3A3551`, build-info `D51F13828DCC5AD825A335482CFA64E8A33CE0E0EDA3F41B434C5FECA45EDF0D`.
- 후보7 위 무창 업데이트 성공(설치 로그 `Installation process succeeded.`). 설치 EXE·build-info 해시 일치, 통제 파일 `48B2611C…660D` 보존, Users 수정 권한·바로가기 2개 확인. 설치 스크립트의 ACL 계정 이름 변환 예외(기존 문제)는 검사 스크립트로 다시 확인했다(14규칙, 미해석 계정 4).
- 후보8 실측(22:47): 바로가기 → Explorer 실행에서 프로그램 창 1개, 새 콘솔 0개. [준비 점검] 23행 모두 OK(관리자 권한은 안내), `XIPL 영상 처리: 정상`. 근거 `work/candidate8-regression/`.
- 실행 전 대조: Baseline `restored-approved-2026-10-15`, DB 4개 BAK SHA-256이 배포 manifest와 일치, Viewer 1.0.12.105·SQL `.\BELLALUN`(호환 목록 안). USB `D:`(`VXVUE1`)·`D:\BellalunWU09` 있음. VXvue 제품·다른 Bellalun 실행 없음.
- 두 전체 실행: 22:47:48 `tools/run_installed_suites.py --suites run-regression,run-winupdate`를 WMI로 분리 실행(PID 7124). 실행 기록 `C:\BellalunAuto 실행 기록\후보8-full-20261105_224748`(설치 대조 파일 1007개 불일치 0).
  - 기본기능 `20261105-224754-64d1e3ef`(22:47~00:57, 129.4분, 종료 1): PASS 22 / FAIL 3 / MANUAL 1 / SKIP 1. FAIL은 `WF_14` UPS 미복원·`XIPL_03` Step 9(알려진 제품 결함)와 `WF_02`.
  - `WF_02` 원인: 개정본 범위(2D·3D-N)는 통과. 자동화 확장 3D-W 촬영에서 Recon/Syn이 75초 대기 안에 DB에 보이지 않아 FAIL(`{0:1,1:2,2:1,3:1}`). 같은 시각 Viewer 로그에 `[DATABASE] 쿼리 시간 제한이 만료되었습니다` 1회와 Recon/Syn 추가(Image84·85, 23:00:47·51)가 있다. 지연과 FAIL의 인과는 확정하지 않았다. Step 6~8 미수행. 같은 후보의 WU 안 `WF_02`는 통과했다. GPU(Quadro P400)는 장치 관리자에 "현재 없음"이고 `No GPUS`는 11-04부터 같다. 대기 시간·기대값은 바꾸지 않았다.
  - WU `20261106-005725-e724d14d`(00:57~02:43, 리포트 105.4분·실행 기록 105.5분, 종료 0): PASS 10 / SKIP 3(`WU_01/12/13` 사람 수행), FAIL 0. WU 안 `WF_14`는 통과.
  - 배포 게이트: `release_gate.py --installed-verification --scope both` 거부 1건(`WF_02` 3D-W 픽스처 FAIL, 알려진 결함 목록 밖). 기록 `work/candidate8-regression/release-gate.json`.
- 공유 ZIP: 보고서 8개 + 증거 PNG 101개(DICOM 제외, 로그 선택했으나 참조 로그 없음). 같은 PC의 다른 한글·공백 경로 `C:\BellalunAuto 공유 검증\다른 위치 후보8`에서 오프라인으로 manifest SHA-256 109개 일치, HTML 상대 링크 107개 유효, 설치판 `verify-share` 정상 0·누락/변조/추가 각 1. 브라우저 화면 표시·다른 PC는 미실측. 기록 `work/공유 검증/후보8 두 전체 오프라인/verification.json`.
- 미완료: 사람 `review.json` 검수(검토자 없음), UAC 직접 선택·취소, 다른 OS·계정, 제거, 다른 PC 공유 확인, 배포 게이트 통과.
- 다음(2026-11-06 사용자 결정): `WF_02` FAIL이 자동화 문제인지 먼저 근거로 확정하고, 자동화 문제면 수정 → 새 후보 → 설치판 두 전체 재회귀 → 게이트 통과까지 진행한다. 기대값·gate는 완화하지 않는다. Claude 세션 한도로 #85를 닫고 AI-Remote-Control Issue #86(Codex `gpt-6.1-sol`, medium)으로 이관했다. 가설·근거 위치는 #86 본문에 있다.

## 2026-11-05 재부팅 후 OSError 수정·후보7 (Issue #85 이어서)

- 사용자 지시: 재부팅 후 바로가기 실행의 준비 점검 `OSError`를 고치고, 수정 후보로 기본기능·WU 두 전체를 한 번 수행한다(DB 4개 복원·서비스/설정 변경·USB 포함 승인). 재부팅은 사용자가 17:25에 했다. Worker는 17:25에 다시 올라왔다.
- 재부팅 직후 상태: VXvue 제품·다른 Bellalun 실행 없음. Codex 데스크톱 앱만 대기 중이다. USB `D:`(`VXVUE1`)·`D:\BellalunWU09` 있음.
- **TCP 표 이상은 재부팅 뒤에도 그대로다.** `Get-NetTCPConnection`·`netstat`·`GetExtendedTcpTable` 모두 상태 값을 틀리게 준다(같은 수신 소켓이 호출마다 CLOSED·FIN_WAIT_1 등으로 바뀜). 수신 소켓만 고르는 목록(`TCP_TABLE_OWNER_PID_LISTENER`)에는 `127.0.0.1:9784`(XIPL.SERVER PID)가 들어 있지만 그 상태 값도 0·1·2·6 중 하나로 나온다. 그래서 `core/preflight.py`의 `-State Listen` gate가 계속 FAIL이다.
  같은 날 11:23에 끝난 WU 실행까지는 gate가 통과했다. 비Microsoft 네트워크 바인딩은 Vieworks `VwFilter` 하나이고, 11-04에 KB5127936·KB5132402가 설치됐다. 원인은 확정하지 못했다. 드라이버·보안·네트워크 설정은 바꾸지 않았고 gate도 바꾸지 않았다.
- 수정(REQ-DIST-002, REQ-QA-005): 출력을 받는 제품 자식 호출 31곳에 표준 입력 NUL 지정, worker는 유효한 콘솔 입력만 상속, 준비 점검 예외 창에 원인 코드·위치·기록 위치·해결 방법. 실패 시험을 먼저 확인했다(잘못된 stdin에서 `WinError 6` 재현).
- 검증: 전체 단위시험 782 passed / 2 skipped / 265 subtests, 정적 7종 이상 없음, readiness 실패 0(기존 경고 2). 독립 검토의 중간 1건(주입한 실행기 경유 호출 2곳)과 사소한 2건을 반영했다. 커밋 `ee43d7d` push.
- 후보7: 소스 `ee43d7d`·dirty=false, 팀 설정 포함 WMI 빌드(PID 1204) 종료 0, 빌드 환경 780 passed / 4 skipped. EXE SHA-256 `6B0C688DCF3693D8C84B087092027962895935E1A59B13745FD57937DAC1CF33`, Setup `37C9DA35AF0688D45F6170F549706DE8C075ADDD9C7906A731663B566AC43A42`, build-info `95c1fbee…174a`. 후보6 위 무창 업데이트 성공, 설치 EXE·build-info 해시 일치, 통제 파일·`config.json` 해시 보존.
- 후보7 실측: 바로가기 → Explorer 실행에서 프로그램 창 1개, 새 콘솔 0개. 수동 [준비 점검] 23행 정상 표시, `OSError` 없음. 실패 행은 `XIPL 영상 처리`(포트 9784) 하나뿐이다. 근거 `work/candidate7-regression/`.
- **두 전체 회귀는 실행하지 않았다.** XIPL 9784 수신 gate가 TCP 표 이상으로 FAIL이라 시작 직후 차단된다. DB 복원·Viewer 실행·USB 쓰기 없음. 새 결과가 없어 공유 ZIP도 만들지 않았다. 사람 검수·UAC 취소·다른 OS/계정·제거는 미완료다.
- 다음: 사용자 결정 대기. (가) gate의 수신 확인을 상태 값 대신 수신 소켓 목록(`TCP_TABLE_OWNER_PID_LISTENER`)과 XIPL.SERVER PID로 읽게 바꾸는 후보8(조건은 같고 측정 방법만 바뀜, 새 빌드라 회귀 승인 필요), (나) PC의 TCP 표 이상을 사람이 먼저 해소(최근 KB·VwFilter 확인 등) 후 후보7로 회귀.

## 2026-11-05 후보6 설치판 인수·회귀 (Issue #85, 회귀 미실행·차단)

- 사용자 승인: 후보6으로 기본기능·WU 두 전체를 즉시 실행한다(DB 4개 복원·서비스 변경·USB 포함). 시작 직전 VXvue 제품은 실행 중이 아니었다. 유휴 Codex 세션만 있었다. USB `D:`(`VXVUE1`)와 `D:\BellalunWU09`가 있었다.
- 신원 대조(17:05): 설치 EXE SHA-256 `C2DD6BAF…7DA3`, build-info SHA-256 `3578aa47…aea4c`. 둘 다 승인 값과 일치했다.
- 첫 실행(공용 바탕화면 바로가기 → Explorer, 일반 권한): 프로그램 창 하나만 떴다. 실행 전후 새 `cmd`·`conhost`·터미널 프로세스는 0개였다. `작업\config.json`이 자동 생성되고 준비 점검 창이 자동으로 열렸다.
- **결함(후보6 FAIL):** Explorer·바로가기로 띄운 GUI에서 준비 점검이 표를 채우지 못한다. 대화상자에 `점검 실패 / OSError`만 보인다. 첫 실행과 수동 [준비 점검] 클릭 모두 재현된다(재현 2/2).
  같은 EXE를 콘솔이 있는 관리자 부모에서 띄운 GUI는 23행을 정상 표시했다. 일반 권한 콘솔의 `selfcheck` CLI도 정상이었다. 소스의 `diagnostics`를 콘솔 없는 `pythonw`로 돌려도 정상이었다.
  원인은 확정하지 못했다. 후보6에서 바꾼 Nuitka `--windows-console-mode=attach`(PE GUI subsystem)로 부모 콘솔 없이 시작한 경우에만 생긴다. `qa_dialogs.refresh`가 예외 이름만 보여 주어 호출 위치가 남지 않는다. Nuitka가 콘솔 없을 때 표준 출력 핸들을 바꾸는 상태를 `pythonw`에서 흉내 냈지만 재현되지 않았다.
- **환경 차단:** 준비 점검의 `XIPL 영상 처리`가 FAIL(`포트 9784 미개방`)이다. `XIPL.SERVER` 로그는 10:27 연결 종료 뒤 멈춰 있었다. 승인 범위의 서비스 변경으로 `XIPL.SERVER`만 종료했고, KEEPALIVE가 17:11에 다시 띄웠다("Listen Initialized").
  재기동 뒤 `127.0.0.1:9784` 접속은 성공했다. 그러나 이 PC의 TCP 연결 표가 상태를 잘못 돌려준다. 9784 행은 상태가 비어 있고, `0.0.0.0:445`는 `FIN_WAIT_1`로 나온다. 그래서 `Get-NetTCPConnection -State Listen` 기반 점검(`core/preflight.py`, 실행 차단 항목)이 계속 FAIL이다.
  gate는 바꾸지 않았다. 이 상태로는 두 전체가 시작 직후 차단되므로 `run_installed_suites.py`를 실행하지 않았다. DB 복원·Viewer 실행·USB 쓰기도 하지 않았다.
- 미완료로 둔 것: UAC 직접 선택·취소, 동의 화면, 진행·중단·완료, 두 전체 회귀, 사람 검수, 새 결과 공유 ZIP, 다른 OS·계정·제거.
- 근거(Git 제외): `work/candidate6-regression/` 화면 5장, `medium-selfcheck.txt`, `repro-*.txt`. 통제 파일 SHA-256 `48B2611C…660D` 보존을 확인했다.
- 다음: (1) TCP 표 이상 해소(재부팅 등, PC 단독 실행 필요) 여부를 사용자에게 확인한다. (2) GUI `OSError`의 원인 수정과 새 후보 빌드에는 새 승인이 필요하다. 후보6으로 회귀를 계속할지, 수정 후보로 바꿀지를 사용자가 정한다.

## 2026-11-05 프로그램 창만 열기

- 사용자 추가 요구: auto 프로그램 실행 시 cmd/터미널 없이 프로그램 창 하나만 표시한다.
- 기존 hide 빌드는 PE console subsystem 3이며 생성된 콘솔을 나중에 숨겼다. GUI subsystem 2 + attach로 바꾸고 실제 PE 헤더 검사 기준도 바꿨다. PowerShell CLI는 파이프/명시적 대기를 사용하며 내부 CLI/worker의 출력·대기는 유지한다.
- 준비 점검(sysinfo/DB)과 DB 복원 서비스 명령, 보고서 환경 수집의 무창 플래그 누락을 실패 시험 후 수정했다. 새 콘솔 생성만 제한하며 SQL/서비스 명령·TC 판정은 바꾸지 않는다.
- 추가 감사로 OCR·Viewer PID·XIPL·WU 근거 수집과 시나리오의 XIPL 정리·Git 조회도 무창 플래그를 적용했다. 수정 후 화면 점유를 명시한 전체 단위시험 **776 passed / 4 skipped / 265 subtests passed**. 콘솔 호출·PE 헤더의 실패 재현을 먼저 확인했다. 실제 PE2·무콘솔 부모의 CLI 출력/종료 코드도 후보6에서 확인했다.
- 실행 중 프로세스가 사라지는 구간에 Tk 화면 시험 2개가 실행된 것을 확인했다. 이후 사용자 지정 화면 점유를 `BELLALUN_DESKTOP_BUSY=1`로 시험/빌드에 명시해 실제 Tk 실행을 차단한다. 이 변수는 시험 코드에만 적용하며 제품 환경 gate를 우회하지 않는다.
- 표시 이름만 반영한 후보5(소스4678633)는 빌드 종료0이나 설치하지 않았다. 후보6(소스 `76d218a1978e6df84457ee0544bd47a77258c7e1`, dirty=false)은 팀 설정 포함 WMI PID11384 빌드 종료0이며 후보4에서 무창 업데이트했다. EXE SHA-256 `C2DD6BAF8AEB3529500661B8CB2038AE1409EB1F1438CC1CAB2015AB79CD7DA3`, Setup SHA-256 `E39089DDCD7DF6C3CECCF6133B7F77CA74E50134BC66A506233C6E7AB7EDB1E2`.
- 실제 PE2/attach, 콘솔 없는 부모에서 버전·공유 ZIP 정상 종료0/누락·변조·추가 각각1과 한글 출력, PowerShell 파이프 종료0을 확인했다. 설치 EXE 해시·Users 수정 ACL·공용 바로가기2개·후보4의 통제 파일 해시 보존도 일치했다. 근거는 `work/qa-candidate6-*-cli-results.json`, `work/setup-candidate6-results.json`과 설치 로그다. 검사 도구의 기존 계정 이름 변환 실패를 보완해 14규칙을 조사했고 ACL은 바꾸지 않았다.
- VXvue 화면 점유 중이므로 실제 Explorer GUI 표시·첫 자동 설정·UAC 취소·제품 회귀·다른 계정/OS·제거는 미완료다. config.json은 아직 없으며 배포 게이트는 passed=false다. 코드·단위시험·설치판 CLI 검증 완료와 제품 검수 완료를 구분한다.
- #80·#84는 사용자 요청으로 닫혔고 기존 예약 작업83은 CANCELLED다. **새 회귀 이슈는 변경 완료 후 사용자의 허락을 받기 전에는 등록하거나 예약하지 않는다.**

## 2026-11-05 자동화 선택 항목 이름 변경

- 사용자 지정 두 항목: **기본기능 체크리스트 자동화 수행**, **Windows Update 체크리스트 자동화 수행**. 실행 화면·확인 계획의 표시를 맞추고 선택한 체크리스트만 실행한다는 안내로 바꿨다. 명령·TC·PASS 기준·실행 범위는 유지한다.
- 실제 Tk 창을 여는 시험은 다른 제품/자동화 프로세스가 실행 중이면 보류한다. Windows 기본 tasklist 조회를 사용하며 추가 의존성이나 제품 환경 gate 변경은 없다.
- 변경 후 전체 시험 754 passed / 4 skipped / 265 subtests passed. 기존 Inno 선택 경로 2개와 VXvue 점유로 보류한 실제 Tk 화면 2개다. 정적 7종·readiness 실패0, 독립 검토에서 중요 결함 없음.
- 현재 VXvue 자동화 실행 중이므로 Bellalun GUI/마우스/키보드/USB를 사용하지 않는다. 소스 검증 후 팀 설정을 포함한 후보5를 WMI로 재빌드하고 무창 업데이트한다. 화면 실측은 아직 미완료다.
- 사용자 최신 지시: **#80은 작업 대체 사유(NOT_PLANNED)로 닫았다. 제품 회귀 완료를 뜻하지 않는다. #84도 닫고 Hub 작업83 CANCELLED·next_run_at=null을 확인했다.** 새 회귀 이슈는 이 변경을 마친 후 내용·시각·PC·모델을 제시하고 **사용자의 허락을 받은 뒤에만 등록·예약한다.** 현재 새 예약은 없다.

## 2026-11-05 첫 사용자 QA 흐름 (후보 준비 완료·UI 실측 대기)

- REQ-QA-001~005: 실행 전 직접 동의, 실행 번호·진행·보고서, 별도 수동 검수, 선택 공유 ZIP, 준비 실패 해결 동선을 구현했다. 엔진·설치기를 재사용하고 TC 기대값·PASS 기준·환경 gate는 변경하지 않았다.
- 독립 검토에서 정상 FAIL 완료 상태, 실제 실패 로그 JSON 공유, WU 마지막 두 단계 진행 표시 3건을 재현 시험 후 수정했다. 재검토에서 추가 중요 결함 없음.
- 최종 전체 단위시험 756 passed / 2 skipped / 265 subtests passed. 정적 7종 통과, readiness 및 workspace gate failed=0. 경고는 기존 미확정 사항·일부 사양 용어·Git 제외 생성물이다.
- skip 2개는 `test_distribution_build.py`의 선택적 `work/InnoSetup6/ISCC.exe`가 없는 버전 조회·Pascal 컴파일 시험이다. 실제 빌드는 별도 설치된 Inno Setup을 `--iscc`로 지정해 검증·Setup 생성을 마쳤다. 첫 GUI/제품 실측을 이 단위 결과로 대신하지 않는다.
- 실제 Tk 동의 화면에서 미체크 시작 금지·직접 체크·취소를 확인했다. 제품 UI·DB 복원은 수행하지 않았다.
- 추가 실측: 이전 실제 전체 보고서 4형식·121개 자료를 한글/공백 다른 경로로 공유·추출하고 네트워크 접근 차단 상태에서 검증했다. 동명 TC 증거 충돌은 실패 재현 후 수정(공유시험 12개), 실행 시각 경계는 재현 후 수정(새 기록 100회 누락 0)했다.
- 후보2 빌드는 실제 보고서 공유 결함을 발견해 중단했다. 후보3은 빌드 환경의 Tk 시험 초기화 실패로 컴파일 전에 멈췄다. 시험을 애플리케이션과 같은 단일 Tk 루트로 정리한 뒤 빌드 환경 전체 시험 756개 통과를 확인했다. 둘 다 설치·회귀에 쓰지 않았으며 후보4를 새 소스 커밋으로 빌드한다.
- 별도 프로필의 headless Edge로 다른 경로의 이전 실제 공유 HTML이 표시됨을 확인했다(DNS 외부 차단·백그라운드 네트워크 비활성화). 현재 후보 새 결과·다른 PC·DICOM 실측은 미완료다.
- 후보4: WMI 분리 빌드 종료 코드 0, `--team-settings` 포함. 소스 `f00005a473098d5fa0b7eb7fc5c980e5717bea3c`, source_dirty=false. 산출물 `work/release-1.0.1-candidate4/`.
- EXE SHA-256 `B650E1C0D69E41FE0E3E89A7FCD63C233A27D5A85AE3E24D2E2B530AF23531AD`; Setup SHA-256 `0A25F058B7CADE6ACB09F573976AD3E7449D86A152773F1CCCABBBB25F09CA29`.
- 실측: Windows 11 Pro 10.0.26200 x64 관리자 세션. `955dd11` 기반 기존 1.0.1 위 무창 업데이트와 후보4 재설치 로그 성공. 설치 EXE 해시 일치, Users Modify ACL(14개 규칙 조회), 공용 바탕화면·시작 메뉴 바로가기, 점검용 파일의 SHA-256 보존을 확인했다. 실제 설정·보고서 보존과 다른 계정 쓰기는 미검증이다.
- 설치판 CLI: version=1.0.1/exit 0; 실제 공유 ZIP verify-share=0; missing/tampered/extra 각 exit 1. 결과 `work/qa-candidate4-cli-results.json`, 설치 결과 `work/setup-candidate4-results.json`. 인수표는 `docs/installation-acceptance.md`.
- 사용자 최신 결정: **실제 UI 회귀는 퇴근 때 사용자가 별도로 요청하기 전에는 실행하지 않는다.** 현재 같은 PC에서 VXvue 자동화 실행 중이라는 답변을 받았으므로 Bellalun GUI·마우스·키보드·USB를 사용하지 않았다. 첫 GUI 자동 설정·완료 후 열기·UAC 취소 실측도 보류. config.json은 아직 없으며 첫 GUI 실행에서 생성해야 한다.
- 다음 요청 시: VXvue UI/USB 점유 재확인 → 첫 실행/UAC 인수 → 변경한 후보의 EXE 해시·두 묶음 약 4시간·DB 복원·USB 범위 제시 → 사용자 답변 후 실행. 이후 사용자 명시로 #80을 닫고 #84 예약을 취소했다. 새 예약에는 별도 허락이 필요하다.

## 2026-11-05 변경 영향별 회귀 기준

- 사용자 결정: 소스에서는 제품을 조작하지 않는 단위시험·정적 검사를 하고, UI 회귀는 빌드한 EXE로 필요한 범위만 수행한다. 단독 TC·기본기능·WU·두 묶음 전체를 영향으로 판단하며 UI 실행 전에 사용자 답변을 기다린다(REQ-REGRESSION-002).
- 설치판 실행 도구에 범위 필수 지정·WF/XIPL 단독 TC 기록을 추가했다. 배포 게이트는 설치판 기록의 실제 파일·해시와 선택 범위만 확인한다. 과거 두 전체 리포트 게이트는 기존 기록 호환용으로 유지한다.
- 이 변경의 검증은 운영 도구의 단위시험·CLI 입출력·정적 검사·readiness로 수행한다. 제품 UI 회귀는 실행하지 않았다. #80은 별도 기존 승인 작업이며, 완료·close를 확인한 뒤 이 변경을 통합한다.

## 2026-11-05 릴리스 게이트 실행과 정식 빌드 (Issue #80)

- 검토: WU·기본기능 자동화를 다시 읽었다. 판정을 틀리게 하는 차단 결함은 없었다. 아래 6건을 시험을 먼저 쓰고 고쳤다(CHANGELOG 2026-11-05 릴리스 게이트 실행 전 검토).
  - 실행 중 커밋 변경과 재개 커밋 혼합을 `source_dirty`로 드러냄.
  - 설치판 build-info 우선, 기본기능 SKIP 제한, 설치판 실행 기록의 WU 목표를 게이트와 같게 맞춤.
  - XIPL Image Processing 창 상태 대기(지난 WU_04 FAIL 원인 후보).
- 주의: 키트 훅(`C:\자동화\tools\project-auto-hook.js`)이 `auto/`에서 프롬프트를 받을 때 `AGENTS.md` 관리 블록을 LF로 다시 써 줄바꿈이 섞인다. 그러면 Git이 수정됨으로 보고 `source_dirty`가 참이 된다(내용 차이 0줄, 07:26 관찰). 회귀 중에는 `auto/`에서 프롬프트를 받지 않는다.
- 다음: 이 커밋에서 `work/gate_run_job.py`(기본기능 전체 → 실시간 WU → 게이트)를 분리 실행한다. 통과하면 같은 커밋으로 정식 빌드 → 설치 → `tools/run_installed_suites.py`로 설치판 두 전체를 다시 수행한다. 결과 기록 커밋은 그 뒤에 한다.

## 2026-11-05 사람이 직접 하는 TC를 SKIP으로 (REQ-VERDICT-002)

- 사용자 결정: 사람이 직접 해야 하는 TC는 기본적으로 SKIP. 대상 WU_01·12·13, WF_16(`tests/winupdate.py` `HUMAN_ONLY_TCS`).
- 릴리스 게이트 WU 목표는 PASS 10 / SKIP 3. 2026-11-05 이전 리포트에는 같은 셋이 MANUAL로 남아 있다.
- 그대로 둔 것: 자동화가 수행했지만 확인하지 못한 MANUAL(Install_01 기준 자료 없음, USB 왕복 미확인)과 `run.py list`의 자동화 등급 표시(`level`).

## 2026-11-04 WU 자동화 정비 (Issue #79, 기존 #2~#9 통합)

- 완료(코드·단위시험·읽기 전용 실측): REQ-WU-002~006, REQ-TRACE-002, REQ-DIST-005. 단위 643개 OK(skip 2), 정적 검사 7종 이상 없음.
- 사용자 결정 반영: USB 미확인 WU_09는 `manual`(사용자 위임), update-watch 예약 등록 안 함(필요할 때 수동 실행), `core/ui.py` 공유 windll 원형 6건을 전용 `WinDLL` 사본으로 옮김(기준선 0건).
- 공용 QA 서버 검증 자료 관리의 Test Case 구역에 WU 체크리스트를 `(TC) R-25-782_Bellalun Viewer_Windows Update 호환성 검증 Checklist.xlsx`로 등록했다. 행·제목은 로컬 기준 체크리스트로 대조했고 WU_12 제목이 Function 열 표기와 같다는 참고 1건이 있다.
- 승인된 실제 실행(2026-11-04 23:28 ~ 11-05 01:14, 커밋 `2039d56`, 수정 없는 소스): `run-winupdate`를 WF03 완료 뒤 WF04 진행 중(23:52)에 강제 종료하고 `--resume`으로 이었다.
  저장점의 8단계를 재사용하고 WF04부터 실행했으며 리포트 meta에 `resumed`·`resume_count=1`·재사용 단계가 남았다. `chain_completed=true`, 감시자 중단 0건.
  결과 `Reports/Result_WindowsUpdate_20261105_011357.*`: PASS 9 / MANUAL 3 / FAIL 1. 목표(PASS 10 / MANUAL 3)와 다른 것은 WU_04 하나다.
  WU_04 FAIL은 XIPL_04 Step 8의 실행 예외("Viewer Image Processing window did not open")다. 같은 실행의 XIPL_02는 같은 `open_process`로 통과했고,
  과거 리포트 219개에 같은 오류가 없으며, 01:37 `run-xipl-04` 단독 재실행은 PASS였다. 1회 발생이라 원인은 확정하지 않았다.
  WU_09 USB 왕복 PASS(`usb_unverified` 없음). WU_10 페이지별 핸들: 56페이지 모두 측정, GDI 3277→3266·USER 6129→6129로 페이지당 증가가 없었다(3-B 원인 판단 아님).
  릴리스 게이트는 WU_04 FAIL, 같은 커밋의 기본기능 전체 회귀 없음, 기존 기본기능 리포트의 `source_commit` 없음으로 거부했다.
- WF14가 Setting 순회의 페이지별 핸들을 리포트에 남기지 않던 SPEC / CODE MISMATCH(REQ-WU-006)를 시험을 먼저 쓰고 고쳤다. Step 7 순회 판정의 actual에 1·2회차 핸들과 증가 요약을 싣는다(판정에는 쓰지 않음). 실물 확인은 다음 WF14 실행에서 한다.
- 공용 서버 Bellalun 지침은 전문 67,392자 중 앞 약 34,000자가 공통 Skill 머리말이다. 시험·판정·TC 대조 작업은 끝까지 읽도록 AGENTS.md에 적었다.
- 다음 시작점: WU_04/XIPL_04 예외가 다시 나오면 Process 버튼 클릭 뒤 창 표시 대기를 조사한다. 릴리스 전에는 같은 커밋에서 기본기능 전체 회귀와 실시간 WU를 다시 돌려 게이트를 통과시킨다.

## 2026-11-04 지식 폴더 서버 동기화 추가 (REQ-KNOW-001)

- `run.py sync-knowledge`와 `core/knowledge_sync.py`를 추가했다. VXvue 저장소의 같은 방식을 옮겼고, 두 저장소는 서로 의존하지 않는다.
- 이 PC를 받는 PC로 `config.json`에 적고 실제로 맞췄다. 새 판 4건을 넣었고 13건 모두 서버 기록 해시와 같다. 예약 작업 `Bellalun_Knowledge_Sync`(평일 11:00)를 등록하고 한 번 실행해 종료 코드 0을 확인했다.
- 사양 근거를 통합 사양서로 옮겼다. 추적성 인용 63건은 문구로 다시 찾았고(검사 73건 이상 없음), 코드·문서의 쪽 번호는 옛 분권과 통합본의 쪽별 문구 대조표로 바꾼 뒤 인용 문구가 새 쪽에 있는지 확인했다.
- 옛 분권 PDF 2개와 텍스트 캐시 2개는 `지식/_이전판/2026-11-04/`로 옮겼다. 상위 `프로젝트_상세.md`와 `지식`의 운영 지침·구현 현황 문서의 인용도 같은 대조표로 고쳤다.

## 2026-10-21 USB 연결 WU_09 재확인 완료

- 이전과 다른 USB(`D:`, `VXVUE1`, FAT32 14.6GB)를 연결하고 후보11 `--clean-env` 실시간 WU 전체를 다시 수행했다(18:27~20:16).
  live, chain_completed=true, PASS 10 / FAIL 0 / MANUAL 3. WU_09의 USB Export와 Import 되읽기(완료 신호 확인)가 PASS다.
- USB의 기존 폴더 두 개는 보존했다. 자동화는 `BellalunWU09`만 만들었고, 제품 UPSHandler가 `D:/BellalunData/Log`에 로그를 썼다(제품 동작).
- 같은 날 AI-Worker(qa-test-02)의 JOB-50 사용량 표시판 적용을 읽기 전용으로 확인했다. 설치 파일 해시가 배포본과 같고 실제 조회가 `status: ok`였다.
- 남은 일: 실제 LTSC·개발 도구 없는 PC·Windows 10·다른 관리자 UAC 검증, 제품 결함 2건 재확인, Install_01·02 기준 자료.

## 2026-10-21 후보11 최소 환경 전체 실행 완료

- 후보11(`56a0bc6`) `--clean-env` 기본기능 전체(10-20 21:17~23:22): 27 TC PASS 23 / FAIL 2 / MANUAL 2.
  FAIL은 기존 제품 결함 WF14 UPS·XIPL03뿐이다(후보8과 같은 FAIL check 7개).
- 실시간 WU 전체(23:22~10-21 01:03): live, chain_completed=true, PASS 10 / MANUAL 3. WU 목표 충족.
  WU_09의 USB 왕복 단계는 USB 분리로 SKIP(`이동식 드라이브 없음`)이다.
- 결과·해시: [호환성 검증 기록](docs/compatibility-2026-10-18.md) 6절. 실행 기록 `C:\BellalunAuto 실행 기록\후보11-cleanenv-20261020_211748`.
- 다음: USB 연결 후 WU_09 USB 왕복 재확인 → 실제 LTSC·개발 도구 없는 PC·Windows 10·다른 관리자 UAC 검증.
- 후보11 산출물은 `work/release-1.0.0-candidate11`(Git 제외)에 있다. 바탕 화면 `BellalunAuto 배포/1.0.0`을 후보11로 교체했고(해시 일치), 후보8은 `1.0.0-후보8(이전)`에 보존했다. 결과 요약은 바탕 화면 `BellalunAuto_최종결과_20261021.txt`다.

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
- 후보11 정식 빌드: 소스 `56a0bc6`(dirty=false), EXE SHA256 `2eb31efe…36f3`, setup SHA256 `43c439ea…bf0c`.
  빌드 내 테스트 469개, 산출물 감사 12/12, PE 미해결 0, 업데이트 설치 후 EXE 해시 일치.
  경계 시험 E1~E6 ALL OK(자체진단 23항목, `%` 작업 폴더는 그 항목만 FAIL·제품 실행은 exit 2로 UI 전 거부).
- 2026-10-20 21:17 후보11 최소 환경 전체 실행 시작. 작업 폴더 `C:\BellalunAuto 작업 공간\후보11 검증 & 테스트 (1) O'Brien #한글`,
  기록 `C:\BellalunAuto 실행 기록\후보11-cleanenv-20261020_211748`(Git 제외). USB 분리 상태다.
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

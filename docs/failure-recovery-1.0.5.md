# 1.0.5 반복 실패 복구 검증

1.0.4 전체 실행에서 추가된 OCR·전송 수신·2D Preview 실패를 조사하고 수정한다. 기존 WF14 UPS와 XIPL03의 알려진 제품 결함, 수동 범위, 판정 임계값은 유지한다. 사용자 요청에 따라 실패 경로를 단독 UI로 확인하고 그 EXE를 배포물로 보존한다.

## 원인과 수정 범위

### Print Overlay OCR

1.0.4는 잘린 마지막 후보를 스크롤한 뒤 행 좌표가 이동하기를 기다렸다. 실제 소스 진단에서 마지막 후보의 `reveal` 단계가 `scroll made no movement`로 중단되는 것을 확인했다. 목록 캡처는 스크롤 후 문구가 바뀌었지만 HWND·Control ID·행 좌표는 같았다. 이 제품은 같은 물리 행 슬롯에 다른 논리 항목을 표시한다. 따라서 좌표 이동만으로 스크롤 완료를 판단할 수 없다.

잘린 경쟁 후보를 버리거나 판독 임계값을 낮추지 않는다. 화면 내용과 행 기하를 함께 관측하고, 스크롤 전후 항목 연결과 선택 직전 신원을 확인해야 한다. 모호한 연결·사라진 컨트롤·해소되지 않은 부분 노출은 실패로 남긴다. 실패 단계·정제 오류·전체 목록 캡처·스크롤 전후 상태를 보존한다.

추가 실측에서 목록 조회 2회가 1.719초를 소모해, 변화가 관측됐어도 기존 1.5초 상한이 안정 표본 수집을 끊는 것을 확인했다. 무변화의 시간 제한은 유지하고 변화 뒤에는 최대 31표본에서 연속 안정 상태를 확인하도록 분리했다. 부분행의 마지막 한 줄은 실제 항목이 아니라 RGB(224,224,224)의 목록 하단 테두리였다. 전체 행의 앞 18줄과 부분행을 대조한 결과 다른 픽셀은 이 마지막 1줄뿐이었다. 원본 캡처는 보존하고, 실제 하단에 잘린 경우의 신원 비교에서만 이 1픽셀과 겹친 스크롤바 영역을 제외한다. 글자 영역의 불일치는 계속 거부한다.

고정 슬롯의 논리 항목은 연속 행의 유일한 이미지 겹침으로 연결하고 부분행을 완전 노출된 세대에서 회수한다. 저장 캡처에서는 16개 연속 행의 유일한 겹침을 확인했다. 모든 행이 온전히 보이는 고정 슬롯도 탐지해 숨은 경쟁 후보를 조사하며, 기하 이동 방식은 원점의 기하·내용·물리 신원을 복원한 뒤 판독한다. 전체 논리 후보에 기존 최대 4판독과 임계값을 적용하고, 선택 화면으로 돌아와 화면 지문과 선택 행을 다시 확인한다.

### 전송과 수신 관측

첫 Queue 배치만 확정해 후발 항목을 빠뜨리는 경로와 HTTP/ZIP/파싱 예외를 정상 0건으로 바꾸는 경로를 재현했다. 신규 Key 집합 수렴과 후발 Key의 Done까지 기다리고, 실제 수신 객체·원본 태그를 대조한다. 수신 조회 시각·응답 해시·건수·정제 오류 종류를 남긴다.

환자에게 여러 Study가 있으면 환자 전체 원본을 이번 전송의 필수 SOP로 요구해서는 안 된다. WF05는 실제 카드 선택 로그와 대조된 session Study Key를 원본·Queue·수신에 일관되게 전달한다. WF06은 기존 카드 클릭 전후의 새 로그로 Study Key를 확인한다. 선택 신원이 확인되지 않는 기존 호출은 Queue 수렴과 실제 수신 대조 계약을 유지한다. 공유 SCP 전체 삭제는 추가하지 않는다.

실제 WF05 소스 진단의 첫 실행은 앞선 OCR 실패가 남긴 설정 저장 팝업 때문에 전송 전에 중단됐다. 이 결과는 수신 실패의 재현이 아니다. 팝업 문구를 확인해 저장하지 않고 닫고 Patient 화면 복귀를 확인했다. 독립 전송 진단과 최종 EXE 수용 결과는 구분한다.

### XIPL 2D Preview

기존 완료 판정은 파라미터 로그에 의존했고, Apply 활성 기대를 visible로만 검사했다. 실제 `IsWindowEnabled`, 파라미터 로그, 영상 영역의 연속 안정 상태를 함께 기다린다. 준비 시간초과와 준비 완료 후 영상 무변화를 구분하며 변화율 기준 0.005를 유지한다. 공용 3D 영상 변화 계산과 완료 로직은 유지한다.

## 검증 진행

담당별 RED→GREEN과 독립 코드 검토를 수행했다. 최종 소스 통합 시험은 **969 passed / 0 skipped / 297 subtests(79.82초)**다. 제품 진단을 정리한 뒤 실제 Tk 시험도 실행했다. OCR 연관 시험82개와 배포 검증 장치의 변조 거부7개도 통과했다. Inno 경로를 명시한 별도 배포 시험은 26 passed / 41 subtests로 컴파일러 검증까지 수행했다. 최종 EXE 수용과 구분한다.

중간 통합 시험은 957 passed / 2 skipped / 297 subtests였다. 보류 2건은 제품 UI 실행 중 실제 Tk 대화상자와 화면이 충돌하지 않도록 하는 보호 조건이다. 이후 발견한 느린 조회·전체 노출 슬롯·하단 테두리 경계를 추가 재현 시험으로 보강한다.

| 소스 단독 진단 | 관찰 결과 |
|---|---|
| WF05 | PASS. 실제 수신 4객체, 대상 Recon 2건과 3D-N/3D-W 수신을 확인했다. |
| XIPL02 | PASS. Apply/Cancel 활성·안정 영상·변화율 0.025302, Apply 후 실제값 유지를 확인했다. |
| WF03 함수 집중 확인 | 앞선 TC 진단에서 잘린 행·느린 조회 상한을 재현했고, 하단 테두리 비교도 보강했다. 보강 후 실제 목록의 논리 후보 38개·화면 세대 20개를 수집하고 1회 판독 프로파일로 Patient ID를 유일하게 선택했다. 원래 화면 복귀와 행 재확인까지 PASS(244.219초)다. WF03 TC 전체의 수용은 최종 EXE로 별도 확인한다. |

설치 수용 도구는 설치 직전 후보 Setup·메타데이터·체크섬 등의 해시를 재대조하고 설치된 build-info를 후보 해시와 연결한다. 각 단독 실행과 종료 시 증거 사본의 크기·해시, 사전 작업 사본의 해시를 확인한다. 실제 검사 코드를 추출한 7개 오프라인 사례에서 정상 입력 수용과 설치 파일·메타데이터·증거 변조 거부를 확인했다.

최종 단독 범위는 WF03·WF08·WF05·XIPL02다. 공통 Print Overlay 선택, 실제 Print 수신, 3D 전송 수신, 2D Preview/Apply를 각각 확인한다. 소스 진단은 원인 확인용이며 배포 수용 근거는 빌드 신원과 일치하는 EXE 결과로 확정한다. 전체 기본기능·WU·다른 OS 검증으로 확대해 표시하지 않는다.

빌드 당시 설치판은 1.0.4였다. 이후 사용자 승인으로 1.0.5 후보를 설치하고 단독 UI를 시작했다. 결과는 아래 [설치판 단독 수용](#설치판-단독-수용과-후속-수정) 절에 있다. 기존 1.0.3·1.0.4 배포 파일11개·실행EXE2개(총13개)와 실행판 보관본 각각1,010개 파일의 해시를 확인했다. 설치1.0.4의1,010개 파일과 config도 일치한다. 기존 작업 자료와 각 진단의 새 보고서·증거는 별도 해시 검증 사본으로 보존한다.

## 후보 빌드와 산출물 검증

2026-11-10 15:07:59~15:41:46 KST(33분47초), 감독 finished/exit_code=0과 컴파일·Inno 성공을 확인했다. 소스는 `4e5101e131c284aa1baab1ddb8853916ad188ed6`, source_dirty=false, compile/tests 생략 없음이다. 빌드 내부 소스 시험도969 passed / 0 skipped / 297 subtests(79.33초)다.

배포물은 `release/1.0.5/`, standalone은 `work/release-1.0.5-run105/BellalunAuto-1.0.5/`에 있다. build-info 등재1,010개와 메타데이터1개(총1,011개)를 전수 대조해 누락·추가·크기/해시 불일치0을 확인했다. 실제 PE subsystem은2이며 EXE의 `--version`·`--help`는 각각 종료0·stderr 없음이다. 버전1.0.5와 예상 도움말을 확인했다.

| 산출물 | 크기(byte) | SHA-256 |
|---|---:|---|
| standalone BellalunAuto.exe | 44,348,416 | `61cb6c4ff1f3cf82523f2d6d9ef6938653267f5bda73b085f5f024ef8c6fc726` |
| BellalunAuto-1.0.5-candidate-setup.exe | 97,416,275 | `1c4dcc087ee71eb913551c33cc09a1f43b09473cbabda02ee4e3a03c63b1e01a` |
| BellalunAuto-1.0.5-release.zip | 96,935,878 | `2b91008f47b9d334b562e8369c65daa3a9f7dc6ec93933f1d5431e6dd1477aa2` |
| build-info.json | 170,435 | `05e88e3962dc7bec8c091e5c722ecf67f7bdb966b208ad468a60796f971ab7c2` |

ZIP은 신규 경로에서 생성한 뒤 최종 폴더로 옮겼다. 최종 위치에서 CRC5개·내부 SHA-256 4개와 Setup/build-info/후보 표식의 원본 일치를 다시 확인했다. 사내 자료를 포함하므로 공개 Git·Release에 올리지 않는다.

**build-info의 gate는 candidate/passed=false이며 후보 파일명과 표식을 유지한다.** 빌드·CLI·해시 성공은 새 EXE의 TC 성공을 뜻하지 않는다. 응답 후 이 패키지로 업데이트하고 WF03·WF08·WF05·XIPL02를 각각 수행해 별도 수용 기록을 만든다. 같은 검증 EXE를 재컴파일하거나 기존 메타데이터를 고쳐 통과시키지 않는다.

로컬 근거는 `work/run105-build/`, `work/implement105/`의 candidate-verification·final-artifacts·release-preservation·rollback-verification·held-install-verification 기록이다. 설치 업데이트·단독UI 기록은 `work/installed-1.0.5-singles-20261110/`에 있다. 다른 PC/OS와 새 전체 회귀도 이번 범위의 실행 결과가 없다.

이전 전체 실행과 조사 근거는 [1.0.4 검증 기록](reliability-2026-11-10.md), 작업 범위는 [복구 계획](superpowers/plans/2026-11-10-failure-recovery.md), 판정 기록의 해석은 [배포 안내](distribution-guide.md)를 따른다.

## 설치판 단독 수용과 후속 수정

2026-11-10 사용자 승인 후 같은 후보 Setup으로 1.0.4에서 1.0.5로 설치했다(17:10:33 완료, 재시작 불필요).

- 설치 전 작업 폴더 1,244개를 해시 검증한 사본으로 보존했다. 설치 뒤 `config.json`을 포함해 바뀐 파일은 0개다.
- 설치판 EXE는 `61cb6c4f…c6fc726`, 소스 `4e5101e1…`, 설치 파일 1,010개 대조 불일치 0이다.
- 사용자 지시로 첫 FAIL에서 멈췄다.

| TC | 결과 |
|---|---|
| TC_Basic_WorkFlow_03 | FAIL. 17:10:47~17:28:02, Step 1 PASS, Step 2(Print Overlay 추가) 수행 중 자동화 중단 |
| TC_Basic_WorkFlow_08 | 미수행 |
| TC_Basic_WorkFlow_05 | 미수행 |
| TC_XIPL_compatibility_02 | 미수행 |

WF03 중단 원문은 `SelectionError: OCR 선택 중단(unreadable): '1 X 2'`다. 제품 결함 판정이 아니다.

- Header Layout 팝업의 항목 창 9개 중 2번째가 네 판독 모두 `1X2`(신뢰도 84~96)로 읽혔다.
- 아래 3개 항목 창(y 621~723)은 팝업 밖이었다. 캡처에는 다른 설정 컨트롤(`60` 입력칸, `Abso…`)이 보였고 신뢰도는 0~47이었다.
- 경쟁 후보 검사는 의도대로 이 영역을 판독 불가 후보로 보고 선택을 거부했다.

증거 51개는 `work/installed-1.0.5-singles-20261110/wf03/snapshots/`에 있고 사본 해시가 모두 일치한다. 1.0.5 후보는 게이트 미통과 후보로 그대로 둔다.

### 후속 수정 (미빌드)

1. 콤보 팝업은 팝업 영역 안의 항목 창만 후보로 읽는다. 실패 증거에 콤보·팝업 영역을 남긴다. 임계값·최대 4판독·경쟁 후보 검사는 그대로다.
2. `core/ui.py`의 `children()`가 `EnumChildWindows` 결과를 하위 창마다 다시 열거하던 것을 한 번 열거로 바꿨다. 같은 창에 문구 조회(WM_GETTEXT)를 깊이만큼 반복하던 비용을 없앤다. 반환하는 창 집합은 같다. 실제 Windows 창 트리에서 중복 14건이 고유 9건으로 줄었다. Viewer 화면에서의 시간 단축은 아직 재지 않았다.
3. 결과 리포트에 직접 확인할 체크리스트 Step 목록을 추가했다(REQ-REPORT-001). 판정과 Step 번호는 바꾸지 않았다.

사용자 요청으로 `run.py reset-environment`를 실행해 4개 DB를 기준 스냅샷으로 복원했다. Print Overlay는 5개에서 0개가 됐다.

새 빌드와 설치, 4개 단독 재실행은 다시 승인받아 수행한다. 공용 UI 조회 계층을 바꿨으므로 REQ-REGRESSION-002 기준의 시험 범위도 함께 확인한다.

## 1.0.6 후보 설치판 단독 수용

9b62878 수정을 담은 1.0.6 후보(소스 `6304688`, dirty=false, 컴파일·시험 생략 없음)를 빌드해 1.0.5 위에 설치했다. 설치 EXE `d1ab0a86…8fcd`, Setup `be7e3d17…5085`, build-info `455578af…501c`다. 후보 표시와 게이트 미통과 상태는 그대로다.

### run106: 선행 데이터 부재

WF03이 5.9초 만에 Step 1 진입 전 `RuntimeError: Viewer XIPL fixture not found: PatientID=DATA_FLOW_MWL_01`로 끝났다. 앞서 사용자 요청으로 DB를 기준 스냅샷으로 복원해 WF01·WF02가 만드는 시험 환자가 없었다. 제품 FAIL이 아니다.

### run107: fixture 준비 후 재실행

2026-11-10 사용자 승인으로 같은 설치판에서 재빌드·재설치·DB 복원 없이 순서대로 실행했다. 각 명령은 clean-env와 작업 폴더 밖 CWD로 실행했다. 실행 전에 설치 1,010개 대조, config 해시, 작업 폴더 1,300개 백업을 확인했다.

| 순서 | 명령 | 결과 | 소요 | 증거 | 게이트 |
|---|---|---|---|---|---|
| 1 | `setup-dicom` | PASS(`DICOM_Server_Setup`) | 109.0초 | 8 | 해당 없음(TC 단독만 지원). exit 0·커밋·build-info 출처·사본 해시 확인 |
| 2 | `run-wf01` | PASS | 156.6초 | 13 | 통과 |
| 3 | `run-wf02` | PASS | 275.0초 | 45 | 통과 |
| 4 | `run-wf03` | FAIL(Step 2 자동화 중단) | 453.2초 | 11 | 실행 안 함(FAIL에서 정지) |
| 5~7 | `run-wf08`·`run-wf05`·`run-xipl-02` | 미수행 | | | |

`setup-dicom`은 `tools/run_installed_suites.py`가 지원하지 않는다(결과 ID가 `TC_`로 시작하지 않음). 그래서 같은 설치 EXE를 같은 조건으로 직접 실행하고 리포트·로그·증거 사본 해시를 남겼다.

WF03 중단 원문은 `SelectionError: OCR 선택 중단(unreadable): 'PRINT_TEST'`다. Step 1(Image Overlay Bottom 추가)은 PASS다. Step 2는 Print Overlay 저장 뒤 DICOM Print 설정 목록에서 `PRINT_TEST` 서버 행을 고르는 곳에서 멈췄다(`core/print_overlay.py`의 `apply_to_print_server`).

- 목록에 행이 1개였고, 캡처에는 `DICOM  PRIN...  PRIN...`처럼 이름 열과 AE 열이 제품 화면에서 말줄임으로 잘려 보였다.
- 4번 판독 모두 `DICOM PRIN... PRIN...` 계열이었고(신뢰도 1~93) 일치 점수는 0.0이었다.
- 경쟁 후보 검사와 판독 기준은 의도대로 동작했다. 기준을 낮추지 않았다.

> **주의** Step 2~6은 선행 중단으로 수행하지 못한 것이다. 제품 FAIL이 아니다.

WF03 소요는 1.0.5 설치판(17.8분, Step 2 Header Layout 판독 중단)에서 7.6분으로 줄었다. 두 실행은 멈춘 지점이 달라 같은 구간의 비교는 아니다. 1.0.5에서 멈췄던 Header Layout `1 X 2` 선택은 이번에 통과했다.

보존 확인: 백업 1,300개 변경 0, 설치 1,010개 일치, config 해시 동일, 1.0.5·run106 증거 유지. 기록은 `work/run107/`에 있다. 다음 조치(목록 열 폭에 잘린 서버 이름 선택 방법 수정 여부, 나머지 3개 실행)는 사용자 결정을 기다린다.

## 1.0.7 후보 설치판 단독 수용 (run108)

1.0.6 WF03의 Print 서버 행 선택을 이름 칸(Control ID 2434) 방식으로 고친 1.0.7 후보(소스 `1a9f49a`, dirty=false, 컴파일·시험 생략 없음, 내부 981 passed)를 1.0.6 위에 설치했다. 설치 EXE `e48c6ddc…d220`, Setup `d0a57030…1c5a`, build-info `df23d957…67b`다. 후보 표시와 게이트 미통과 상태는 그대로다.

| 순서 | 명령 | 결과 | 소요 | 증거 | 게이트 |
|---|---|---|---|---|---|
| 1 | `run-wf03` | PASS | 295.2초 | 16 | 통과 |
| 2 | `run-wf08` | FAIL(Step 7 자동화 오인) | 188.0초 | 26 | 실행 안 함(FAIL에서 정지) |
| 3~4 | `run-wf05`·`run-xipl-02` | 미수행 | | | |

WF03은 1.0.5(17.8분 중단)·1.0.6(7.6분 중단)과 달리 끝까지 수행해 PASS다.

WF08은 Step 1~6(Print Overlay 저장·적용, 2D 필름 Overlay, 서버 수신·프리뷰 일치)과 Step 7의 3D-N 대조가 PASS다. 3D-W 대조에서 자동화가 다른 장비의 job을 집었다.

- 3D-W 필름을 보낸 직후 다른 장비(`QXLink`, `14INX17IN`)의 job 371이 먼저 도착했다. 그 서버 프리뷰는 다른 환자의 요추 영상이다.
- 자동화는 새 job이 하나라도 생기면 그 job을 비교해 유사도 0.690으로 FAIL을 기록했다.
- Bellalun이 보낸 job 372(`BELLALUN`, `8INX10IN`)는 8초 뒤 도착했다. 같은 유사도 함수로 오프라인 대조하면 0.982(기준 0.96)다. 이 값은 참고 증거이고 TC 판정은 아니다.

> **주의** Step 7 이후의 교차 대조와 나머지 Step은 수행하지 못했다. 제품 FAIL로 보지 않는다.

후속 수정(미빌드): WF08은 calling AE가 DB의 Station AE(`DICOM_COMMON.StationAETitle`)와 같은 job만 비교에 쓰고, 건너뛴 다른 장비 job을 증거에 남긴다(REQ-REGRESSION-001).

보존 확인: 백업 1,326개 변경 0, 설치 1,010개 일치, config 해시 동일, 1.0.5·1.0.6·run106·run107 증거 유지. 기록은 `work/run108/`에 있다.

## 1.0.8 후보 설치판 단독 수용 (run109)

WF08의 job 선택을 Station AE 기준으로 고친 1.0.8 후보(소스 `990f647`, dirty=false, 컴파일·시험 생략 없음, 내부 986 passed)를 1.0.7 위에 설치했다. 설치 EXE `69b235c4…8648`, Setup `ec614fea…b194`(97,436,783바이트), build-info `4cc76da3…c9c0`다. 빌드는 20:31:09~20:53:53이다. 후보 표시와 게이트 미통과 상태는 그대로다.

WF03은 1.0.7에서 PASS했고 이번 수정과 무관해 사용자 승인대로 제외했다.

| 순서 | 명령 | 결과 | 소요 | 증거 | 게이트 |
|---|---|---|---|---|---|
| 1 | `run-wf08` | PASS | 168.6초 | 29 | 통과 |
| 2 | `run-wf05` | PASS | 165.5초 | 5 | 통과 |
| 3 | `run-xipl-02` | PASS | 114.9초 | 8 | 통과 |

이번 실행 중에는 다른 장비의 job이 Print SCP에 도착하지 않았다. 비교한 job은 모두 calling AE `BELLALUN`이다. 따라서 다른 장비 job을 건너뛰는 경로는 실화면에서 다시 관측되지 않았고, 단위 시험(`tests/test_printscp_jobs.py`)으로만 확인됐다.

보존 확인: 백업 1,342개 변경 0, 설치 1,010개 일치(커밋·EXE 해시 일치), config 해시 동일, 1.0.5~1.0.7 후보와 run106~run108 증거 유지. 기록은 `work/run109/`에 있다. 알려진 제품 FAIL(WF14 UPS, XIPL03 Step 9)은 이번 범위 밖이라 그대로다. 전체 기본기능/WU 회귀는 하지 않았고 사용자 결정을 기다린다.

## 1.0.8 후보 설치판 전체 회귀 (run110)

사용자 지시로 같은 1.0.8 설치판(`990f647`, EXE `69b235c4…8648`)에서 `run-regression` → `run-winupdate`를 순서대로 실행하고, 게이트 허용 목록 밖 문제가 있으면 다음 묶음으로 가지 않게 했다. 기본기능 회귀는 21:29:52~23:08:07(98.4분)에 끝났고 27 TC 중 PASS 21 / FAIL 4 / MANUAL 1 / SKIP 1이다. 기본기능 게이트가 "알려진 결함 외 FAIL 14건"으로 거부해 WU는 실행하지 않았다.

| TC | 결과 | 실패 원문 | 분류 |
|---|---|---|---|
| TC_Basic_WorkFlow_14 | FAIL | Step 7 `device.ups` 값 `EATON El` → `None` | 알려진 제품 결함(허용 목록) |
| TC_Basic_WorkFlow_15 | FAIL | Step 1~3 PASS 뒤 `StorageScpError: Storage SCP DICOM 파싱 오류`(공유 SCP 객체 185개 중 일부에 StudyInstanceUID·SeriesInstanceUID 없음) | 새 문제. 수신 관측 단계 중단, Step 4~7 미수행 |
| TC_XIPL_compatibility_03 | FAIL | Step 1 `XIPL 3D Apply timed out after 120.0s`(진행·창 닫힘·파라미터 관측 모두 없음) | 새 문제. 알려진 Step 9 이전에 중단, Step 3~9 미수행 |
| TC_XIPL_compatibility_04 | FAIL | Step 6 기대 `TEST_2D_A_M.pim`, 표시 `TEST_2D_B_M.pim` | 새 문제. Step 7~8 미수행 |

1.0.4 전체 회귀에서 PASS였던 WF15·XIPL04가 이번에 FAIL이다. WF03·05·08·XIPL02는 PASS로 돌아왔다. 원인 조사 결과는 아래 절에 있다. 미수행 Step을 제품 결함으로 세지 않는다.

보존 확인: 설치 1,010개 일치, config 해시 동일, 백업 1,363개 변경 0, 증거 사본 280개 검증. 기록은 `work/run110/`, 리포트는 작업 폴더 `Reports/Result_20261110_230803.json`이다.

### run110 새 FAIL 원인 조사와 수정 (미빌드)

사용자 지시로 새 FAIL 3개를 run110 리포트·증거·Viewer 로그로 조사했다. 세 개 모두 자동화 원인이고 제품 결함이 아니다. 판정 기준과 허용 목록은 바꾸지 않았다.

| TC | 근거 | 원인 | 수정 |
|---|---|---|---|
| WF15 | 관측 `studies_before_filter=49`, `patient_studies=49`, 파싱 오류 10건. 서버에는 이 환자 Study가 12개다 | `tests/workflow15.py`가 환자 없이 `wait_received_stable`을 불러 공유 SCP 전체를 받았다 | `_wait_received`가 `DATA_FLOW_MWL_01`을 지정한다(WF07과 같은 방식) |
| XIPL03 | Preview 캡처(22:47:52)에 "Receive Synthetic image"와 회색 Apply. Apply 클릭 뒤 `Do Post Reconstruction` 없음. 정상 실행은 Apply 뒤 2초 안에 `Terminate PostReconThread` | `eNoti:5` 로그만으로 Preview 완료를 판정해 비활성 Apply를 눌렀다 | `_post_recon_preview_ready`가 Apply·Cancel 활성까지 기다리고, Apply는 활성 버튼만 누른다 |
| XIPL04 | 제품 로그 `Process Parameter: RCCRL / TEST_2D_A_M.pim`, `RCCRM / TEST_2D_B_M.pim`. 22:53:33 첫 Image Process 전에 `Select Thumbnail` 로그 없음 | A 영상 썸네일 클릭이 무시돼 직전 B 영상을 읽었다 | `_select_2d_confirmed`가 `Select Image ... Step ID` 로그로 선택을 확인하고 최대 3번 다시 누른다 |

XIPL03 Step 7(Preview 변화율 0.0178)은 로딩 화면을 캡처해 통과한 것이다. 수정 뒤에는 Preview가 끝난 화면을 캡처해 판정한다.

검증: 새 시험 6개를 먼저 실패로 확인한 뒤 구현했다. 전체 990 passed / 2 skipped(Inno 경로 미지정) / 299 subtests, Inno 경로를 지정한 배포 시험 26 passed, 정적 검사 6개 통과. 실화면 확인은 새 빌드 뒤 사용자 승인을 받아 한다.

## 1.0.9 후보 설치판 수용 (run111)

사용자 지시(#102): 자동화 문제는 묻지 않고 고치고, 제품 결함만 보고한다. 1.0.9(4508bb4)를 빌드해 1.0.8 위에 설치하고 단독 3개 → 기본기능 전체 → WU 순서로 실행했다.

| 실행 | 결과 | 게이트 |
|---|---|---|
| WF15 단독 | PASS(139.0초) | 통과 |
| XIPL03 단독 | 알려진 결함 Step 9만 FAIL(559.8초). Step 8 Apply 처리 PASS | 통과 |
| XIPL04 단독 | PASS(368.7초) | 통과 |
| 기본기능 전체(98.7분) | PASS 23 / FAIL 2 / MANUAL 1 / SKIP 1 | 거부(XIPL03 Step 1) |

- WF14는 알려진 UPS 결함만 FAIL이다. WU는 게이트 거부로 실행하지 않았다.
- XIPL03(회귀): Preview 완료 로그(01:58:24.532 eNoti:5) 뒤 Apply·Cancel은 활성이었지만, Preview 스레드 종료 로그 전인 01:58:26에 Apply를 눌렀다. Viewer는 Apply를 처리하지 않았고 종료 로그는 timeout 뒤 창을 닫은 02:00:26에야 남았다. run110 실패도 같은 순서였다.
- 같은 날 성공한 실행(단독 00:33:26 eNoti:5 → 00:33:28 종료 로그 → Apply → 00:33:40 Apply 종료)은 모두 종료 로그 다음 Apply를 눌렀다. 사람이 Preview가 끝나기를 기다린 뒤 누르는 순서와 같으므로 자동화 원인으로 본다.
- 수정: `_post_recon_preview_ready`가 GPU 유무와 관계없이 Preview 스레드 종료 로그까지 기다린다. 판정 기준과 허용 목록은 바꾸지 않았다.

## 1.0.10 후보 설치판 단독 (run112)

- XIPL03 단독: Preview 완료 로그와 Apply·Cancel 활성 뒤에도 Preview 스레드 종료 로그를 120초 기다리다 timeout 됐다(Step 1 중단). 스레드는 스스로 끝나지 않았다. 1.0.10 수정(종료 로그 대기)은 잘못된 가정이었고 되돌렸다.
- 다시 본 근거: 성공한 run111 단독은 Apply 클릭 직후(00:33:28.181) Preview 스레드가 끝나고 창이 닫혔다. 즉 종료 로그는 받아들여진 Apply 클릭이 남긴다. 실패한 run110·run111 회귀는 eNoti:5 0.6초 뒤, Preview 영상이 막 그려지던 때 클릭해 로그도 창 변화도 없었다. 성공한 실행은 eNoti:5 1.3초 뒤에 눌렀다.
- 수정: `_click_3d_apply_confirmed`가 클릭 뒤 5초 안에 창 닫힘 또는 Post Recon 로그를 확인하고, 없으면 최대 3번 다시 누른다. 끝내 안 되면 TC를 중단한다. 사람이 반응 없는 버튼을 다시 누르는 것과 같으므로 자동화 원인으로 본다. 판정 기준과 허용 목록은 그대로다.

## 1.0.11 후보 설치판 전체 수용 (run113)

| 실행 | 결과 | 게이트 |
|---|---|---|
| XIPL03 단독(170.6초) | Step 1~8 PASS, Step 9 알려진 결함 FAIL | 통과 |
| 기본기능 전체(97.0분) | PASS 23 / FAIL 2 / MANUAL 1 / SKIP 1 | 통과 |
| WU 전체(77.1분) | PASS 10 / SKIP 3 | 통과 |
| 합동 릴리스 게이트 | WU·기본기능 리포트 모두 커밋 2630d0b | 통과 |

- 기본기능 FAIL 2건은 알려진 제품 결함뿐이다: WF14 Step 7 UPS 설정 미복원, XIPL03 Step 9 Apply 후 TEST_3D 이름과 10개 값이 기본값으로 돌아감.
- MANUAL(Install_01)과 SKIP(WF16, WU_01·12·13)은 사람 전용으로 미리 정한 TC다.
- run110에서 새로 나온 FAIL(WF15, XIPL03 Step 1, XIPL04)과 run111·run112의 XIPL03 Step 1은 모두 자동화 수정으로 해소됐다.

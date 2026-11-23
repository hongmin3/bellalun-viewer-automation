# BellalunAuto·VXvueAuto 오류 조치 조사

2026-11-23에 두 Windows 설치판의 설치, 시작, 준비 점검, 시험 실행, 중단·복원, 결과 및 전달 경로를 소스에서 확인했다. BellalunAuto는 후보 `1.0.0.005`와 후속 변경을, VXvueAuto는 `18586f5`를 기준으로 봤다.

| 상황 | BellalunAuto 확인 위치 | VXvueAuto 확인 위치 | 사용자가 바로 할 일 |
|---|---|---|---|
| 권한·작업 폴더 때문에 시작 실패 | `bellalunauto/app.py`, `bellalunauto/gui.py` | `packaging/launcher.py` | 현재 폴더와 조치가 표시된 창에서 작업 폴더 또는 관리자 재실행을 선택한다. |
| 설치 준비, OCR·자료 누락, 설정 손상 | `packaging/BellalunAuto.iss`, `bellalunauto/prerequisites.py` | `core/install_prepare.py`, `core/gui_setup.py` | 설치 준비 기록에서 실패 항목을 보고 설정 위치나 준비 화면을 연다. |
| DICOM 웹 포트, C-ECHO·서버 설정 | `bellalunauto/app.py`, `core/dicom_settings.py` | `core/startup_menu.py`, `core/user_launch.py` | 실제 오류가 발생한 웹 포트·DICOM 포트·AE Title을 확인하고 PC별 설정에서 수정한 뒤 다시 점검한다. |
| USB 미연결 | `core/run_preparation.py`, `tests/winupdate.py` | `core/startup_menu.py`, TC08·TC13 | 시험 USB를 연결하거나 팝업에서 계속을 선택한다. 계속하면 해당 단계가 MANUAL이다. |
| 디스크·메모리·공유 보존 저장소 | `core/resource_budget.py`, `core/execution_session.py` | `core/startup_menu.py`, `core/run_session.py` | 공간 부족은 표시된 경로의 용량을 확보한다. 조회 실패는 연결·쓰기 권한과 설정 경로를 확인한다. |
| 사용자 중단·복원 대기 | `bellalunauto/recovery_gui.py`, `tools/recover_preservation.py` | `core/run_matrix.py`, `core/run_history.py` | BellalunAuto의 복원 재개에서 실행을 선택한다. VXvueAuto에서는 연동 원복 실패 경로와 원래 모드를 확인한다. |
| TC 중단·시간 초과·실제 제품 FAIL | `run.py`, `core/result.py` | `core/regression.py`, `core/failure_explanations.py` | 실행 기록에서 실패 단계와 증거를 확인한다. 저장점 손상이나 실제 제품 오류는 실패 조건을 보존한다. |
| 기록 저장·공유 ZIP 실패 | `bellalunauto/qa_dialogs.py`, `bellalunauto/share.py` | `core/qa_handoff.py` | 열린 파일을 닫거나 쓰기 가능한 폴더를 선택한다. 원본 누락은 결과 폴더에서 먼저 확인한다. |

BellalunAuto는 화면 메시지 상자 호출 28곳과 런타임 단계 모듈 25개를 조사했다. VXvueAuto는 런타임 TC 파일 14개와 결과 기록 호출 후보 326곳을 조사했다. 이 수치는 정적 검색으로 확인한 코드 위치다. 장비에서 모든 오류 분기를 재현하는 수용 시험은 별도다.

우선 보강할 범위는 설치 준비 실패의 세부 원인, 시험 중 개별 장비·제품 오류별 조치, 손상된 저장점의 재개 가능 여부, 공유 ZIP의 원본 누락과 쓰기 실패 구분이다. 자동 복원은 선택한 실행과 검증된 보존 기록을 기준으로 실행한다.

# Bellalun 변경 작업과 TC 판정

새 TC, 기준서 개정, 보고서 변경은 아래 표에서 해당 행부터 시작한다. 명령은 [프로젝트 의존성](../requirements.txt)을 설치한 Python으로 저장소 루트에서 실행한다.

| 바꿀 대상 | 기준과 구현 위치 | 먼저 검증할 것 |
|---|---|---|
| 기본기능·Windows Update(WU) 체크리스트 판본 | [사양 REQ-TRACE-001·002](../SPEC.md) → [판본과 TC 추적표](../traceability.json) → [기준서 선택](../core/tc_basis.py) | 기본기능은 `basic`의 `개정 TC`, WU는 `windows_update`의 `Checklist`를 사용한다. 선택한 파일의 승인 해시, 시트, TC ID와 제목을 확인한다. |
| TC 절차·자동화 범위 | [범위 원장](../automation_scope.json), [TC별 함수 연결](../traceability.json) → [시나리오](../tests) | Step과 Expected 원문 셀, 인용한 사양·매뉴얼 절, 실제 호출되는 함수와 WU에서 재사용하는 TC를 확인한다. 인용이 비어 있으면 직접 확인한 범위를 기록한다. |
| 보고서·에이전트 판정 | [보고서 작성](../core/result.py) → [판정 채점](../core/evidence_evaluation.py) → [회귀 시험](../tests/test_evidence_basis.py) | 결과 JSON의 `meta.checklist_basis`, 대상 행의 `tc_basis`, 실행 방식과 관찰값을 대조한다. 기준서가 맞아도 이번 제품 관찰이 없으면 `UNVERIFIED`다. |

## 기준서 또는 TC를 바꿀 때

실행기·배포 작업은 [구조 안내](architecture.md)와 [배포 안내](distribution-guide.md)에서 담당 경로를 찾는다. 새 기능은 [사양서](../SPEC.md)에 해당 REQ, 검증 방법과 12절의 구현·시험 연결을 함께 작성한다.

1. 적용할 제품·문서 판본을 확인한다. 구판과 개정판에서 같은 ID의 제목, Step, Expected가 달라졌는지 대조한다. 예를 들어 구판의 WF04는 Overlay이고 개정본의 WF04는 2D 수동 DICOM Send다.
2. 개정 범위가 확인되면 추적표의 해당 판본·해시·쪽·SRS·TC 연결을 고친다. 설치 자료도 바뀌면 패키지 매니페스트의 해당 역할과 해시를 확인한다. 구현 변경은 SPEC 12절에 연결한다. 사내 원본은 설정으로 지정한다.
3. 아래 명령으로 원문과 인용을 대조하고 합성 기준서로 정상·충돌·과거 보고서 사례를 시험한다. `config.json`은 해당 PC의 실제 기준서 및 지식 폴더를 가리켜야 한다.

새 TC도 이 절차를 따른다. 체크리스트에 행을 넣은 뒤 [추적표](../traceability.json)와 [범위 원장](../automation_scope.json)에 같은 ID·등급을 등록한다. 완전자동 TC는 실제 구현 함수까지 연결한다. 기준서에만 행이 있거나 완전자동 TC의 함수가 빠지면 해당 묶음의 기준서 확인이 실패한다. 정규 회귀에서도 실행할 TC는 [실행 순서](../run.py), WU는 [WU 매핑](../tests/winupdate.py)과 해당 실행 체인에 추가하고 선택·실행 시험을 갱신한다. 보고서에 TC 근거가 연결되는 것과 정규 회귀가 그 TC를 실행하는 것은 각각 검증한다.

```powershell
python tools/traceability.py --config config.json
python -m pytest tests/test_evidence_basis.py -q
```

## 공식 체크리스트 단계 원장

[단계 원장 생성기](../tools/official_checklist_ledger.py)에 공용 QA 원본 WF·WU와 #191에서 보관한
`coverage-evidence-index-212.json`을 지정한다. 원장에는 원문과 사내 증거 위치가 있으므로 PC1의
비공개 작업 폴더에 생성한다.

```powershell
python tools/official_checklist_ledger.py --wf $wf --wu $wu --baseline-index $prior --output $ledger
```

원본 SHA-256, 시트·행·셀·줄과 취소선 상태를 고정한다. 번호가 같은 Expected는 조작 후보를 제시한다.
같은 번호가 여러 번 나오거나 번호가 없으면 근거 리뷰로 연결한다. 각 줄의 실제 실행 증거는 비어
있는 상태에서 시작한다. #191 보고서는 행 단위 비교 기준으로 참조한다.

| 우선 단계 | 공식 원본 위치 | 구현·판정과 남은 증거 |
|---|---|---|
| 3D DICOM 전송 | WF Basic Function Checklist K16:L16, WU Checklist G12:I12 | [WF05](../tests/workflow05.py)에서 Queue와 받은 SOP를 대조한다. Raw/Syn 등록·수신과 Recon 누락은 실패다. 화면과 범위마다 새 조작·수신 증거가 필요하다. Recon 없는 시험 검사는 UI로 만들거나 승인된 비식별 픽스처를 가져온 뒤, DB로 Raw와 Recon 부재를 확인하고 Queue·SCP를 각각 관측한다. |
| 2D·3D 처리 취소 | WF K30:L31, WU H9:I10 | [XIPL02](../tests/xipl_flows.py)는 Apply 결과를 기준으로 새 Preview를 취소한 뒤 2D 원본과 DB 식별, ImageAction 파일을 비교한다. 3D Recon/Syn 파일·DB의 Cancel 경로는 후속 구현 대상이다. |
| 매체별 왕복 | WF K20:L20, Screening Test C18:D18, WU G14:I14 | [WU09](../tests/winupdate.py)와 [USB 검증](../core/usb_verification.py)을 기반으로 매체의 원본 파일·영상 검증과 가져오기를 연결한다. USB와 CD는 별도 실행 증거 및 사전 자원 확인이 필요하다. |
| Windows 전후·계정·Kiosk | WU G6:I6, G17:J18 | 승인 격리 환경에서 빌드·KB, Viewer 설치와 실행, OS 권한, 장비·Launcher, 재시작 전후 상태를 읽는다. 본 환경을 바꾸기 전에 복원 경로를 검증한다. |

## 제품 판정의 근거를 제출할 때

자료와 구현 위치만 확인하려면 다음과 같이 조회한다.

```powershell
python run.py --config config.json evidence-basis --kind basic --tc TC_Basic_WorkFlow_04
python run.py --config config.json evidence-basis --kind windows_update --tc TC_WindowsUpdate_02
```

에이전트는 원문과 이번 보고서를 읽어 독립적으로 제출 JSON을 작성한다. 정본을 확인하면 해시·시트·ID 셀·Expected 셀·구현 함수를 `citation`에 넣는다. 이번 실행의 제품 판정을 제출하려면 해당 JSON의 `report_sha256`도 적는다. 실행 감독 기록인
`Runs/<실행 번호>/run.json`에서 확인한 번호를 `--expected-run-id`에 넣는다. 소스 CLI 단독 실행에서는
`preservation/<실행 번호>/journal.json`을 확인한다. 제출 보고서와 별도로 확보한 번호를 써야 이번 회차와
대조할 수 있다. [구판 충돌 제출 예시](examples/conflict-claim.json)는
WF04의 해시가 다르고 유효한 제품 근거가 없는 경우다. 이전 XLSX의 Pass 열, 다른 회차 보고서,
저장점에서 재사용한 결과로 이번 실행의 PASS를 주장하면 채점에서 거부한다.

```powershell
python run.py --config config.json evidence-basis --kind basic --tc TC_Basic_WorkFlow_04 --claim claim.json --report result.json --expected-run-id <실행번호>
```

보고서가 없으면 `--report`와 `--expected-run-id`를 생략한다. 종료 코드 0은 제출 내용의 일치를 뜻하며, 예시처럼 `UNVERIFIED`도 올바른 답일 수 있다. 종료 코드 2이면 출력의 불일치 필드 또는 입력 오류를 확인한다.

인수인계에는 검사한 커밋, 제품·기준서 판본, TC와 원문 위치, 구현 함수, 실행한 검사와 보고서 위치, 미수행 범위를 남긴다. 전체 소스 검증은 [저장소 검증 명령](../botyard.json), 실제 설치판 수용 범위와 승인 절차는 [시험 안내](testing-guide.md)를 따른다.

## 짧은 요청으로 새 자동화를 만들 때

에이전트가 사용자에게 보여야 할 결과와 실행 계기를 한 문장으로 적고 [사양서](../SPEC.md)에서 재사용할 REQ와 코드를 찾는다. 기존 자료에서 입력 판본, 필요한 PC·서비스, 허용된 상태 변경과 관찰 방법을 채운다. 판정 근거나 조작 범위를 달라지게 하는 미확정 사항만 사용자에게 묻는다.

| 사용자가 요청한 일 | 에이전트가 먼저 정할 것 | 완료를 확인할 자료 |
|---|---|---|
| 새 제품 시험 묶음 | 적용 기준서·판본·시트, 고유 ID, 실행 순서와 담당 함수 | 원문 행에서 보고서까지 대표 한 건을 추적한다. 같은 ID의 구판과 구현이 빠진 사례를 거부하는지 시험한다. 현재 기준서 선택기는 기본기능과 WU를 지원한다. 제3의 묶음은 기준서 역할·로더·실행 등록·추적 검사·보고서 연결을 추가한다. |
| 설치·배포 점검 | 실제 배포물, 대상 PC, 기본 실행 경로와 요구 환경. [배포 안내](distribution-guide.md)와 [설치판 게이트](../tools/installed_release_gate.py)를 확인한다. | 빌드 신원, 설치 경로의 파일, 사용자가 처음 여는 화면을 확인한다. 화면 잠김·필수 장비 부재 시 실제 끝낸 단계와 차단된 단계를 남긴다. |
| 기존 자동화 시간 단축·예약 실행 | 기준 회차, 바꿀 구간, 비교할 입력·판정과 복원 조건. 시간 비교는 [회귀 소요 기록](regression-timing.md)을 참조한다. | 같은 조건에서 TC별 판정·제외·복원 결과를 대조한 뒤 소요 시간을 비교한다. 예약 작업은 첫 실행의 산출물과 재시작 시 중복 효과도 확인한다. |

작업 기록에는 **발동 조건 → 입력과 판본 → 기대 효과 → 관찰 방법 → 실패·재개·복원 기준**을 남긴다. 정상 한 건과 잘못 통과하기 쉬운 한 건으로 먼저 검증한다. 출시나 설치판 수용이 요청에 포함되면 승인된 PC와 빌드에서 사용자 경로를 확인한다.

다른 Worker에 넘길 때는 이전 작업 번호, 커밋·빌드, 마지막 확인 단계, 복원 여부, 재사용할 증거와 다음 한 단계를 적는다. 미완료 작업은 후속 이슈 번호로 잇는다. 설치·예약·성능처럼 체크리스트 밖의 자동화에는 해당 산출물을 확인하는 검사를 붙이고, 제품 TC의 인용·판정은 위의 채점 명령으로 검사한다.

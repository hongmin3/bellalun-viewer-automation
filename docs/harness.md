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

## 제품 판정의 근거를 제출할 때

자료와 구현 위치만 확인하려면 다음과 같이 조회한다.

```powershell
python run.py --config config.json evidence-basis --kind basic --tc TC_Basic_WorkFlow_04
python run.py --config config.json evidence-basis --kind windows_update --tc TC_WindowsUpdate_02
```

에이전트는 원문과 이번 보고서를 읽어 독립적으로 제출 JSON을 작성한다. 정본을 확인하면 해시·시트·ID 셀·Expected 셀·구현 함수를 `citation`에 넣는다. 이번 실행의 제품 판정을 제출하려면 해당 JSON의 `report_sha256`도 적는다. [구판 충돌 제출 예시](examples/conflict-claim.json)는 WF04의 해시가 다르고 유효한 제품 근거가 없는 경우다. 이전 XLSX의 Pass 열이나 저장점에서 재사용한 결과로 이번 실행의 PASS를 주장하면 채점에서 거부한다.

```powershell
python run.py --config config.json evidence-basis --kind basic --tc TC_Basic_WorkFlow_04 --claim claim.json --report result.json
```

보고서가 없으면 `--report`를 생략한다. 종료 코드 0은 제출 내용의 일치를 뜻하며, 예시처럼 `UNVERIFIED`도 올바른 답일 수 있다. 종료 코드 2이면 출력의 불일치 필드 또는 입력 오류를 확인한다.

인수인계에는 검사한 커밋, 제품·기준서 판본, TC와 원문 위치, 구현 함수, 실행한 검사와 보고서 위치, 미수행 범위를 남긴다. 전체 소스 검증은 [저장소 검증 명령](../botyard.json), 실제 설치판 수용 범위와 승인 절차는 [시험 안내](testing-guide.md)를 따른다.

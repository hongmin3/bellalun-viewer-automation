# Bellalun·VXvue 공통 자동화 프레임

Bellalun Viewer 자동화(`Bellalun Viewer/auto`)와 VXvue 자동화(`vxvue/auto`)는 제품이 다르다.
하지만 실행 화면, 진행 표시, 결과 레포트는 같은 모양으로 맞춘다. 이 문서는 두 저장소가 함께 지키는 계약이다.
두 저장소의 `frame/` 폴더에 같은 내용으로 있으며, 한쪽만 고치면 검사가 실패한다.

사용자 결정(2026-11-23):

- 실행 화면은 공용 WinForms(PowerShell) 창 하나를 두 제품이 같이 쓴다.
- 공통 코드는 두 저장소에 같은 사본으로 두고 해시로 검사한다. 별도 공용 저장소는 만들지 않는다.
- 레포트 산출물은 두 제품 모두 HTML·JSON·체크리스트 xlsx 세 가지로 맞춘다.

## 1. 공유하는 것과 제품마다 다른 것

| 구분 | 공유(두 저장소가 같은 파일) | 제품마다 다름 |
|---|---|---|
| 목록 | `frame/frame.lock.json`의 `files`에 적힌 파일 | 그 밖의 모든 파일 |
| 예 | 레포트 표시 계약(`core/report_layout.py`), 이 문서, 검사 도구 | 제품 UI 조작, TC 시나리오, 판정 근거, 제품 설정, 빌드 방식 |

공유 파일은 제품 이름·컨트롤 ID·판정 근거를 담지 않는다. 제품 값은 호출하는 쪽이 넘긴다.

> **예시** 레포트 제목의 "Bellalun Viewer"나 "VXvue"는 각 제품의 `core/result.py`가 `report_layout`에 넘긴다.

## 2. 두 제품이 같은 모양으로 맞출 것

### 2.1 판정 값

TC와 Step 판정 값은 `PASS`, `FAIL`, `MANUAL`, `SKIP`, `BLOCKED` 다섯 가지다.
색은 `core/report_layout.py`의 배지 색을 화면과 레포트에서 같이 쓴다.

### 2.2 처음 쓰는 사람용 실행 화면 흐름

설명을 따로 듣지 않아도 화면만 보고 끝까지 갈 수 있게 다섯 단계로 보인다.

1. **첫 화면**: 이 프로그램이 하는 일 세 줄, 지금 할 일 버튼 하나("준비 점검 시작"), 마지막 결과 요약.
2. **준비 점검**: 맨 위에 결론 한 줄("시작할 수 있습니다" 또는 "시작 전에 해결할 문제 N개"). 아래 표에 상태·항목·확인 결과·해결 방법을 두고, 고칠 수 있는 항목은 설정 화면을 바로 연다.
3. **실행 선택과 동의**: 실행할 체크리스트, 걸리는 시간, 실행 중 마우스·키보드를 쓰지 말 것, DB 복원 여부를 보이고 모두 체크해야 시작한다.
4. **진행**: 단계 n/N, 지금 하는 TC, 경과 시간, 최근 기록 줄, 안전 중단 버튼.
5. **결과**: 큰 결론(모두 통과 / 사람이 확인할 항목 있음 / 실패 있음 / 중단), 사람이 볼 항목 목록, 레포트 열기·결과 폴더 열기·전달 ZIP 버튼.

화면 문구는 쉬운 한국어로 쓰고, 오류 원문과 경로는 그대로 보인다.

구현은 공유 파일 두 개다.

| 파일 | 하는 일 |
|---|---|
| `core/frame_ui.ps1` | Windows PowerShell 5.1의 WinForms로 다섯 화면을 그린다. ASCII로만 쓰고 보이는 글자는 모두 JSON으로 받는다. `-Snapshot <png>`이면 그린 화면을 저장하고 바로 닫는다. |
| `core/frame_ui.py` | 화면별 데이터(`home`·`inspect`·`confirm`·`progress`·`result`)를 만들고 창을 띄운다(`show`). 화면 맨 위의 단계 표시, 색(`PALETTE`, 레포트 배지와 같은 색), 결과 결론 문장(`outcome_headline`)을 정한다. |

제품 코드는 점검 결과·실행 대상·동의 항목·결과 행을 이 함수들에 넘기기만 한다. 제품마다 다른 선택값(VXvue의 모드·테마)은 `inspect(options=..., views=...)`로 넘긴다.

### 2.3 진행 기록

실행 엔진은 진행을 실행 폴더의 `events.jsonl`에 한 줄씩 남기고, 화면은 그 파일을 읽어 보인다.
화면과 엔진은 이 파일과 종료 결과 파일로만 주고받는다. 화면이 닫혀도 실행은 계속된다.

한 줄의 모양(`core/frame_ui.append_event`):

```json
{"time": "14:03:22", "tc_id": "TC_Basic_WorkFlow_03", "index": 3, "total": 27, "message": "실행 시작"}
```

`index`·`total`이 있으면 진행 화면이 "단계 3/27"과 진행 막대를 보인다. 없으면 마지막 TC 이름만 보인다.

### 2.4 결과 레포트

산출물은 다음 세 가지다. 같은 실행의 파일은 같은 `Reports` 폴더에 둔다.

| 파일 | 내용 |
|---|---|
| `Result_<날짜_시각>.html` | 사람이 읽는 레포트 |
| `Result_<날짜_시각>.json` | 같은 내용의 원본 데이터 |
| `Checklist_Result_<날짜_시각>.xlsx` | 기준 체크리스트 사본에 판정을 적은 파일 |

HTML 절 순서와 목차 이름은 `core/report_layout.py`의 `SECTIONS`가 정한다. 두 제품은 목차를 `standard_nav()`로 만들고, 시험에서 `section_order_problems()`로 본문 순서를 확인한다.
이번 실행에 내용이 없는 절은 빼되 순서는 바꾸지 않는다.

| 순서 | 절 id | 목차 이름 | 내용 |
|---|---|---|---|
| 1 | `overview` | 결과 요약 | 전체 판정, 판정별 TC 수, 소요 시간 |
| 2 | `user-steps` | 직접 확인할 Step | 사람이 수행·확인할 기준 체크리스트 Step |
| 3 | `failures` | 실패 원인 | FAIL TC의 원인과 다음 조치 |
| 4 | `manual` | 수동 확인 | MANUAL·BLOCKED 등 사람이 볼 항목 |
| 5 | `references` | 참고 정보 | 필수 수동 확인과 구분한 참고 |
| 6 | `skipped` | SKIP 사유 | 실행하지 않은 TC와 이유 |
| 7 | `tc-results` | 전체 TC 결과 | 검색·판정 필터가 있는 표 |
| 8 | `tc-details` | 상세 근거 | 기준 원문과 이번 실행 비교, 증거 |
| 9 | `slow-steps` | 오래 걸린 단계 | 시간 기록 상위 단계 |
| 10 | `run-info` | 환경·원본 | 실행 환경, 원본 파일, 같은 실행의 다른 산출물 |

새 절이 필요하면 `SECTIONS`에 먼저 넣고 두 제품에 반영한다. 목록에 없는 절 id로 목차를 만들면 `standard_nav()`가 오류를 낸다.

### 2.5 설치 위치와 폴더

사용자 결정(2026-11-23): 두 제품 모두 `C:\` 바로 아래 제품 폴더 하나에 프로그램·설정·결과를 둔다. AppData나 별도 "작업 폴더"를 쓰지 않는다.

| 위치 | Bellalun | VXvue |
|---|---|---|
| 설치 폴더(프로그램) | `C:\BellalunAuto` | `C:\VXvueAuto` |
| 설정 | `Settings\config.json` | `Settings\config.json` |
| 결과·근거·기록 | `Reports`, `Evidence`, `Log`, `Runs` 등 | `Reports`, `Evidence`, `Log`, `Sessions` 등 |
| 시험 자료 | 설치판 `resources` | `TestData` |

지킬 것:

- 설치 폴더는 상속 권한을 끊어 관리자·SYSTEM만 고칠 수 있게 한다(`core/frame_install.harden`). `C:\` 아래 새 폴더는 기본으로 "인증된 사용자 수정"을 물려받아, 관리자 권한으로 도는 자동화의 실행 파일·DLL을 일반 사용자가 바꿀 수 있기 때문이다.
- 일반 권한으로 화면을 여는 제품(Bellalun)만 데이터 폴더에 사용자 수정 권한을 준다. 항상 관리자 권한으로 실행되는 제품(VXvue)은 사용자 쓰기 폴더를 두지 않는다.
- 예전 위치(Bellalun `C:\Program Files\BellalunAuto\작업`, VXvue `%LOCALAPPDATA%\VXvueAuto\Workspace`)의 설정·결과는 업데이트 때 새 위치로 복사한다(`core/frame_install.migrate`). 이미 있는 파일은 덮어쓰지 않고, 예전 폴더는 지우지 않는다.
- 화면·문서에는 "작업 폴더" 대신 실제 폴더 이름(`C:\BellalunAuto\Reports` 등)을 쓴다.

### 2.6 체크리스트 대응과 결과 xlsx·레포트 문장

사용자 요청(2026-11-23): 결과를 실제 체크리스트 TC에 맞춰, 처음 보는 사람도 읽기 쉽게 같은 모양으로 낸다.

TC 대응 규칙:

1. 체크리스트 행과 자동화 결과는 TC ID가 정확히 같을 때만 잇는다. 번호·제목이 비슷해도 다른 TC ID면 잇지 않는다.
2. 결과가 없는 체크리스트 행은 판정 "미수행"과 이유를 적는다.
3. 체크리스트에 없는 자동화 단계(환경 준비·점검)는 "체크리스트 밖 준비 단계"에 따로 모은다.
4. 같은 TC ID의 결과가 여럿이면 FAIL > BLOCKED > MANUAL > PASS > SKIP 순으로 한 판정을 정한다.

결과 xlsx:

- 기준 체크리스트 사본 맨 앞에 "결과 요약" 시트를 둔다(`core/frame_checklist.add_summary_sheet`). 결론 한 줄, 실행 정보, 레포트 링크, 판정 합계, 체크리스트 순서의 TC별 판정·확인할 내용·체크리스트 위치, 체크리스트 밖 준비 단계, 판정 뜻이 들어간다.
- 체크리스트 시트의 제품별 결과 칸(VXvue K열 `Pass / Fail / N/T`, Bellalun 결과 열, Bellalun WU K~L열)은 각 제품의 기존 결정대로 둔다.

레포트 문장:

- 판정 뜻은 `core/report_layout.VERDICT_MEANINGS` 한 곳에 둔다. HTML 레포트(목차 아래 "판정 뜻")와 결과 요약 시트가 같은 문장을 쓴다.
- 결론 문장은 사람이 할 일을 먼저 말한다(예: "사람이 확인할 TC가 2개 있습니다").

## 3. 한쪽에서 바꾸면 다른 쪽에도 반영하는 규칙

공유 파일을 고치는 작업은 같은 작업 안에서 형제 저장소까지 끝낸다.

1. 한쪽 저장소에서 공유 파일을 고친다.
2. 그 저장소 루트에서 `python frame/sync_check.py --update-lock`으로 잠금 해시를 갱신한다.
3. `python frame/sync_check.py --propagate`로 공유 파일과 잠금을 형제 저장소에 복사한다.
4. 두 저장소에서 각자의 검증 명령을 실행한다(Bellalun은 `botyard.json`의 `verify`, VXvue는 `python run.py selfcheck`).
5. 두 저장소에 각각 커밋하고 push한다. 커밋 메시지에 `frame:` 머리말과 형제 저장소 커밋을 적는다.

지킬 것:

- 공유 파일에 한 제품만 쓰는 값이나 분기를 넣지 않는다. 제품 차이는 호출하는 쪽에서 넘긴다.
- 형제 저장소에 다른 세션의 작업이 진행 중이면 복사하지 않고 그 사실을 보고한다. 그동안 두 저장소의 검사는 실패한다.
- 공유하지 않는 파일(제품 UI, TC, 판정)은 이 규칙의 대상이 아니다. 다만 2절의 모양을 바꾸는 변경이면 이 문서를 먼저 고쳐 두 제품이 같이 따르게 한다.

검사:

- `python frame/sync_check.py`는 잠금 해시와 이 PC에 있는 형제 저장소의 사본을 비교한다.
- Bellalun은 `tests/test_frame_sync.py`, VXvue는 `selfcheck/test_frame_sync.py`가 이 검사를 각자의 검증 게이트에서 실행한다.
- 형제 저장소가 없는 PC에서는 사본 비교를 건너뛰고 안내만 출력한다.

## 4. 현재 차이와 맞추는 순서

조사일 2026-11-23 기준 차이다. 단계가 끝나면 이 표를 갱신한다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 공유 사본 검사·반영 규칙(이 문서, `frame/sync_check.py`) | 완료 |
| 2 | 레포트 통일: Bellalun CSV·TXT 중단, 공통 절 목록(`SECTIONS`)으로 목차·순서 통일, VXvue 체크리스트 xlsx를 결과와 같은 폴더·같은 시각 이름으로 저장 | 완료 |
| 3 | 공용 WinForms 실행 화면(2.2)과 진행 기록(2.3). 사람이 여는 기본 흐름을 두 제품 모두 이 화면으로 바꿈(Bellalun `bellalunauto/frame_launch.py`, VXvue `core/frame_vxvue.py`) | 완료 |
| 3-위치 | 설치 위치·폴더 통일(2.5), 설치 폴더 권한 정리, 예전 위치 자료 복사 | 완료(설치판 수용 확인 전) |
| 3-후속 | Bellalun의 PC별 설정·수동 검토·공유 ZIP 창과 무인 실행 화면(Tk), VXvue의 상세 설정·이력·PC 준비 창을 공용 화면으로 옮김 | 예정 |
| 4 | 각 제품 EXE로 화면·레포트·설치 위치 수용 확인(실행 전 사용자 승인) | 예정 |
| 5 | 체크리스트 TC 대응과 결과 xlsx "결과 요약" 시트, 판정 뜻 공통 문장(2.6) | 완료 |

알려진 차이(맞출지 정하지 않은 것):

| 항목 | Bellalun | VXvue |
|---|---|---|
| 종료 코드 | FAIL 1, 설정 오류 2, 비정상 3 | FAIL 2, BLOCKED 3, 환경 중단 4 |
| TC 판정 우선순위 | FAIL > BLOCKED > MANUAL > PASS > SKIP | FAIL이 있으면 FAIL, PASS가 없으면 BLOCKED·SKIP·MANUAL 순 |
| EXE 빌드 | Nuitka | PyInstaller |

판정 규칙과 종료 코드는 결과 의미를 바꾸므로 사용자 확인 없이 맞추지 않는다.

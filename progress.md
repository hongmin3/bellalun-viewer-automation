# 진행 상태
## 2026-11-13 재부팅 후 1.0.13 소스 검증과 실물 선행조건

미커밋 WIP를 보존해 공용 사전/시험 후 보존·차이 복원·생성 Image 한정 정리·정리 재개를 통합했다.
독립 검토의 중요 지적(복원 verified 뒤 서비스/완료 증명/정리/최종 보고서 실패가 pending에서 빠짐)을
실패 시험으로 재현해 제품 시작 전 durable 마무리 대기로 막았다. 미시작 확인의 잠금 해제도 검증했다.
기존 사용자 AGENTS.md 수정은 보존하고 커밋에서 제외한다.

백엔드와 TC 독립 검토의 중요 지적을 실패 시험으로 확인해 수정했고 최종 재검토의 추가
Critical/Important는 없다. 실제 NAS/제품 UI 수용 통과를 뜻하지 않는다.

최신 소스 전체 시험: `python -X utf8=0 -m pytest tests -q`, 실제 Inno 경로 지정,
1407 passed +302 subtests passed, skip0, 136.33초. 로그는 work/run664-release-source-tests.log다.
코드 정적4종·추적성·WU 매핑·범위 문서 검사 실패0, 완료 정리85문서/삭제0/실패0,
readiness·workspace gate 실패0을 확인했다. workspace는 앱 시험을 실행하지 않아 위 pytest를 별도로 수행했다.
미확정 외부 입력·기존 문서/생성 캐시 경고는 남긴다. 신규 후보 빌드·설치는 이 결과와 별도다.

WF14는 UPS Import 제외·변경값 유지로 수정했고 과거 원시 보고서 SHA를 유지한 별도 사양 재평가만
PASS로 기록했다. XIPL03은 우측 기본값과 img/Overlay 적용값 분리, 최신 Study 사본 선택,
Apply timeout 증거 저장과 재시작 대조를 추가했다. 실제 제품 재시험 전이므로 XIPL03 전체 PASS가 아니다.
잘못된 제품 결함 제외 목록은 비웠다. [사양 재평가](docs/spec-reevaluation-2026-11-13.md)를 따른다.

과거 1,938개/152.51GiB inventory 모델: 로컬 방식 C513.55/USB15.11GiB → 공유 방식
C21.60/USB0.79/NAS상한324.27GiB. 현재 빈 Image는 사용자 삭제 결과다. 개선 성과와 분리한다.
실제 NAS 합성 probe는 재부팅 후 WinError1326 인증 오류로 전용 폴더 생성 전에 막혔다.
기존 공유 연결·설정·자격증명은 바꾸지 않았다. 실제 SMB 통합 통과가 아니다.

현재 DATA는 PATIENT/STUDY 각1, SERIES/INSTANCE/INSTANCE_GROUP/FRAME0, QC_STUDY1이다.
승인 Baseline에는 DB4개만 있고 전체 Image/manifest가 없다. 일부29영상으로 전체 복구를 주장하지 않는다.
현재 상태 보존·Baseline 적용·실영상 확보/대조와 신규 설치판 전체 수용은 남아 있다.

설치판1.0.11은 유지했다. 새 패키지는 ZIP해제→Setup설치→설치된Auto GUI→기본/WU전체→복원/결과/
Image정리→60초자동닫기와 모든취소조건으로 검증한다. 녹화·편집·업로드는 하지 않는다.
NAS 재연결·실영상 준비 후 새 EXE/해시·시간·입력점유·DB/설정/USB변경에 대한 답변을 기다린다.
P10 제품 설치패키지/검증된 argv·DB ReleaseVersion, P14 Windows 대상/계정·WinRM·공유 VHD 잠금은
외부 입력과 실물 수용이 남아 있다. [검증 범위](docs/practical-preservation-validation.md)를 따른다.

## 직전 1.0.12 P1~P14 구현·로컬 검증 기록

사용자가 #132 보고서 전체와 GUI 자동 닫기를 승인했다. 실행마다 원상복원 여부를 선택한다. 이전 설치판 1.0.11과 녹화·과거 결과는 보존했다.

- 구현: 사전 파일/DB 사본과 해시 검증, 선택 복원과 journal 기반 재개 신원, 볼륨별 자원 예산, 저장 실패 부분/비상 결과, 감독 최종 실행 기록, 준비 점검 통합, 60초 GUI 자동 닫기와 버튼 취소.
- 추가 구현: Release Note 버전별 기준 추출과 Install01 실제 구성 수집, 검증 프로필 기반 설치 수명주기 CLI, 명시 로그 원인 증거, UI 비용 계측·Setting 닫기 공통화, 자동 범위 문서, 원격 인증 API·대화형 Windows 실행/취소/회수 기반.
- 독립 검토의 중요 지적: 복원 세대 별도 파일 제거(journal 자체 사용), 서비스 RUNNING 검사, DB staging 용량 합산, 단독 USB 보존 연결, 기본기능 비상 결과, 원격 비정상 종료 구분과 보관 증거 회수 경로를 보완한다.
- 최종 전체 단위시험: 1257 passed / 302 subtests passed, 127.47초, skip 0. `python -X utf8=0 -m pytest tests -q`와 실제 Inno 경로로 수행했고 시험 전후 소스 해시 변경 0이다. Windows 기본 문자셋에서 실패한 시험 JSON 읽기 2곳은 UTF-8을 명시했다. 로그: work/followup-remote-release-tests.log.
- 원격 후속: 인증 binary 전송·해시 캐시·기존 묶음 갱신·실시간 진행/최근 로그·기본 6시간과 예상 시간 검사·모든 시작 후 복원 미확인 잠금을 보강했다. 독립 검토의 추가 중요 결함 3건을 수정했고 재검토의 추가 Important/Critical은 없다. 원격 시험 73개 통과. 엔진의 강제 중지는 복원을 완료하지 못할 수 있어 성공으로 표시하지 않는다.
- 후보 빌드: 1.0.12 Setup 생성, 당시 선행 시험 1216개·302 subtests 통과. 실제 EXE 버전/도움말 종료 0과 체크섬 2개 일치를 확인했다. build-info source_commit eee1055 / source_dirty=true이며 GUI·엔진·core는 해당 커밋과 같다. 원격 후속은 별도 소스다. 실물 기본기능/WU 입력이 없어 후보로 남기고 설치판은 유지한다.
- 최종 로컬 검사: 코드 구조 4종·추적성·WU 매핑·자동 범위 문서, 사내 상세 문서 동기화, readiness와 workspace gate 실패 0. cleanup은 문서 91개 검사·삭제 0·실패 0이다. 미확정 사양·기존 문구·중복 문서·생성 캐시 경고는 남아 있다. workspace gate는 앱 시험을 실행하지 않아 위 pytest를 별도로 수행했다.
- 실제 Viewer UI/DB 복원·제품 설치/제거·서버 배포·Windows 원격 수용은 이번 구현 중 실행하지 않았다. 실제 설치 패키지·검증된 무인 argv와 원격 PC/계정 및 VHD 공용 잠금 연동이 실물 단계의 선행조건이다.
- 읽기 확인: 지정한 Release Note의 1.0.12.105 기준 파일 15개를 설치 경로에 연결했다. DB 버전 기준은 원문에 없어 미확정이다. 실제 config는 바꾸지 않고 work의 별도 JSON으로 남겼다.

현재 사용법은 [실행 보존 안내](docs/followup-reliability.md), 범위는 [자동 생성 현황](docs/followup-scope.md), 원격 운영 조건은 [원격 안내](remote/README.md)를 따른다. 이전 제품 FAIL과 QC/Dose SR의 과거 복원 미확인은 유지한다.

## 직전 실물 검증 기록 — 2026-11-13 새벽 f247d21

아래는 후속 1.0.12 개선 이전의 실제 실행 기록이다. 당시 구현·제외 범위와 복원 제한을 보존하며 새 후보의 수용 결과로 사용하지 않는다.

WF14 전체 행 판독, WF15 Overlay OCR·원본 검사 선택, WU09 실행 전 USB 체크리스트와 단독 실행을 구현했다. WU11은 같은 WF14 전체 행 판독을 재사용한다. 사람 전용 TC는 사유가 있는 SKIP으로 남긴다. VXvue 코드 검토·이번 적용·추후 후보는 [검토 및 실행 기록](docs/tc-upgrade-2026-11-12.md)에 있다.

기존 로컬 d4c36fa를 보존하며 원격 변경을 일반 merge했다. VXvue ff-only pull은 로컬 변경과 겹쳐 중단돼 읽기만 했다. 설치판 1.0.11·녹화 원본은 보존했고 빌드·설치·재부팅은 수행하지 않았다.

### 실제 실행과 판정

| 실행 | 시간(KST, 2026-11-13) | 결과 | 증거 |
|---|---|---|---|
| 초기 소스 개별 WF14·WF15·WU09 및 WU11 매핑 | 00:00~00:32:58, 복원 포함 | 자동화 실패를 확인해 수정. 당시 FAIL 보존 | `work/run648/` |
| 실제 소스 GUI 기본기능 전체 | 01:11:20~02:50:28, 99.0분 | PASS 23 / 기존 제품 FAIL 2 / MANUAL 1 / SKIP 10 | `work/run652-gui/runtime/Reports/Result_20261113_025023.json` |
| 최종 실제 소스 GUI WU 전체 | 04:55:22~06:11:21, 체인 75.7분 | PASS 10 / SKIP 3. 216개 확인 중 PASS 212 / SKIP 4 | `work/run655-retry/runtime/Reports/Result_WindowsUpdate_20261113_061110.json` |

- WF14는 목록 13페이지·89행·849항목 전수 판독과 Import 후 상세값 대조가 PASS다. 전체 TC의 UPS 미복원 FAIL은 유지했다.
- WF15는 16개 확인이 PASS다. 원본 검사의 클릭 로그 Key·Step·Overlay·Queue·수신 UID를 대조했다.
- WU09는 USB Export와 Import 완료 Imported 1 / Skipped 0, DB·파일·재검색 근거가 PASS다. WU11의 전 행 열거와 상세값 복원도 PASS다.
- 기본기능 36개 결과에는 준비용 2개가 포함된다. Install07~09는 이번 구현·회귀에서 제외한 추후 항목이다. Install01은 승인 기준값 미확정 MANUAL을 유지했다.
- 자동화 등급: 기본기능 37개 FULL 24 / PARTIAL 3 / SKIP 10, WU 13개 FULL 10 / SKIP 3. FULL은 실제 PASS와 다른 구현 등급이다.

### 실행 중 발견한 자동화 문제와 검증

빈 Print Overlay 부모의 DB 개수 대조, WF15 Import 복사본 선택, WF09 IMG 형식 잔존, 자정 이후 No Result 안내창을 실패 시험 후 수정했다. GUI의 426,991자 로그 한 줄 표시 정지는 파일 원문 보존·화면 길이 제한으로 수정했고 후속 WU에서 실제 완료 화면을 확인했다. 기본기능의 최초 GUI 실행 기록은 running 상태로 보존하며 엔진 완료 리포트와 구분한다.

WU 1차는 제품 SQL 조회 시간 초과와 이후 디스크 경고 모달을 관찰해 원인을 구분했다. 이번 생성물 4개 폴더를 USB 별도 보관소로 파일별 해시 대조 후 옮기고 원래 경로 연결을 유지했다. 다음 시도는 저장점 원자 교체 WinError 5로 중단됐다. 원래 추후였던 저장점 재시도를 회귀 차단 수정으로 승격했다. 실제 Windows 읽기 핸들로 같은 오류를 재현하고, 5·32·33만 최대 8회/총 대기 1.95초로 제한했다. 지속 실패는 원본 보존과 오류 전달을 유지한다. Tool 단계 미수행이 WU03 SKIP/일부 PASS가 되던 판정도 FAIL로 바로잡았다. 과거 결과는 수정하지 않았다.

- 최종 전체 단위시험: 1042 passed / 2 skipped / 299 subtests passed(84.62초). `work/run656-final/unit-final.log`에서 전체 시험 종료 0을 확인했다.
- 최종 WU 종료 직후 소스 해시 전수 대조가 일치했다. 이후 리포트 부록 등급 타일만 수정했다. 기존 기본기능 원본의 결과 전체·원본 SHA256이 같은 표시 사본을 `work/run656-final/Reports/`에 생성해 FULL24·SKIP10 표시를 검증했다. 제품 조작·TC 판정 경로는 바꾸지 않았다. 독립 코드 검토 Critical/Important 없음.
- 최종 정적 검사·WU 매핑·추적성·문서 동기화·readiness와 workspace gate 실패 0. 워크스페이스 gate는 앱 시험을 실행하지 않아 pytest 1042개를 별도로 수행했다. 미확정 후속 사양·과거 문서·로컬 생성물 경고는 실행 실패와 구분한다.

### 복원과 남은 제한

최종 WU의 자동 복원은 06:14:04 완료했다. DB 차이 없음, 설치 작업 폴더·USB·이미지 inventory·원본 시험환자 파일 해시 일치, Bellalun Service RUNNING이다. 감독의 `restoration.json`, `db-restored-diff.json`, `restored-services.json`, `summary.json`을 확인했다.

앞선 기본기능 실행에서는 기존 QC 이미지 6개가 같은 이름으로 덮어써졌다. 실행 전 내용 사본이 없어 해당 시점의 바이트 복원을 확인할 수 없다. 수정 시각만 되돌려 복원 성공으로 표시하지 않았다. 이후 실행은 QC 전체도 백업했다. 초기 단독 실행의 Dose SR도 이전 내용 해시가 없어 그 시점의 바이트 동등성은 미확인으로 남긴다. 이 제한은 후속 복원 성공으로 지우지 않는다.

당시 남은 일은 제품 UPS·XIPL03 결함 수정 후 확인, Install01 기준 수집과 Install07~09 무인 설치 수명주기, 발표자료 별도 지시, VXvue 미적용 후보였다. 해당 실행은 종료됐다. 이후 구현 상태와 현재 실물 조건은 `NEXT_WORK.md`를 따른다.

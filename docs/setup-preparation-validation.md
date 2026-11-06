# 1.0.2 설치 구성품 준비 검증

2026-11-06 소스 `5004de0970893999694752e16f1e054209b83e6c`, dirty=false를 컴파일·테스트 생략 없이 빌드했다. [구현 계획](plans/install-prerequisites.md)과 SPEC의 REQ-DIST-007 범위다. 제품 전체 회귀 결과는 이 새 EXE에 대해 확보하지 않았다.

## 다른 PC에 가져갈 파일

`release/1.0.2/BellalunAuto-1.0.2-candidate-setup.exe` 하나에 실행 파일, OCR 설치 파일, 승인 Baseline4개·체크리스트·매뉴얼이 들어 있다. 같은 폴더의 `SHA256SUMS.txt`로 파일 해시를 대조한다. 사내 자료를 포함하므로 공개 Release에 올리지 않는다.

제품 Bellalun과 제품 설치가 준비하는 Server·SQL·XIPL, 외부 시험 서버·USB는 기존 준비 사항이다. Setup은 Baseline 파일과 설정을 준비하며 사용자 DB 복원이나 제품 시험은 시작하지 않는다. 새 EXE의 제품 회귀 승인이 없어 파일 이름은 candidate다.

| 파일 | SHA-256 |
|---|---|
| Setup | `6353235bbe3c0bb88a8291cdbd3afeaaf13ea23cf600c69affd689ae915f5468` |
| EXE | `67f7eaf5a89818b072dfb80a1f88676f713fa5ea5518da5d168576f240a804bd` |

## 확인 결과

- 전체 소스 시험: 820 passed / 4 skipped / 267 subtests. 새 설치 준비 시험은 모두 실행했다. 정적7종·readiness·workspace 검사 통과.
- 고정 OCR 설치 파일: Tesseract5.5.3, 26,573,224바이트. 공식 release digest와 SHA-256을 대조했고 빌드·설치 준비 단계에서 다시 검사한다. 라이선스를 함께 넣었다.
- 승인 자료를 배치한 실제 소스 실행: 신규 설정·기존 설정 준비 각각 종료0, Baseline4개 확인, 기존 설정 해시 보존.
- 새 포터블 EXE: 신규 작업 폴더 설정 생성0, 재실행0·설정 보존. 잘못된 기존 OCR 경로는 종료1·실패 요약·설정 보존을 확인했다.
- 기존1.0.1 위 무창 업데이트: 13:48:10~13:48:34, Setup 종료0, 설치 로그의 자동 준비 종료0. 설치 파일1,010개 해시 불일치0, Users Modify 확인.
- 기존 작업 파일381개 누락·변경0, config 보존. 추가 파일은 `install-preparation.txt` 하나다. 기존 OCR5.4 실행·영어 언어 파일을 재사용했고 승인 자료·기존 설정 보존을 요약에 표시했다.
- 독립 코드 검토에서 기존 OCR 설정과 다른 경로로 성공하는 문제, PATH의 작업 폴더 실행 후보 검사를 보완했다. 두 재현 시험의 실패를 확인한 뒤 수정했다.

로컬 상세 기록은 `work/setup-verification-5004de0/verification.json`, `work/portable-preparation-5004de0/verification.json`, `work/install-prep-smoke-5004de0/verification.json`에 있다. 설정 내용과 사내 자료는 Git에 넣지 않는다.

## 배포 폴더 정리

후속 요청으로 포터블 ZIP 생성을 중단하고 현재1.0.2 ZIP도 제거했다. 현재 릴리즈는 Setup·build-info·SHA256SUMS·후보 표식4개이며 체크섬2개가 일치한다. 아래5개 이동과3개 해시 대조는 ZIP 삭제 전의 이력이다. Setup의 해시는 바뀌지 않았다.

사용자 요청으로 현재 파일5개를 `release/1.0.2/`로 옮겼다. Setup·ZIP·build-info의 SHA-256 3개를 이동 후 다시 대조해 모두 일치했다. 이후 빌드는 `release/<버전>/`에 최종 파일만 모으고 같은 버전의 기존 파일은 덮어쓰지 않는다. 중간파일은 `--output`에 남긴다.

구버전 배포·컴파일 폴더18개(9.67GiB)를 제거했고 저장소 내 구버전 Setup·ZIP 잔존0개를 확인했다. 빌드 메타데이터·로그와 포함된 실행 증거는 `work/release-build-records/`에 보존했다. 과거 문서의 구버전 배포 경로는 이제 실물이 없는 역사 기록이다. 정리 내역은 `work/release-cleanup-result.json`, 이동 검증은 `work/release-layout-verification.json`에 있다.

폴더 처리 변경 후 소스 시험은821 passed / 4 skipped / 267 subtests다. 이번 변경은 빌드 도구와 문서뿐이며 위1.0.2 실행 파일을 다시 컴파일하지 않았다.

## 확인하지 않은 범위

OCR이 전혀 설치되지 않은 다른 PC에서 NSIS 설치를 끝까지 수행하는 검증은 남아 있다. 누락·변조·설치 실패·시간 초과 경로는 격리 시험으로 검증했으며, 실제 이 PC에서는 정상 기존 OCR을 재사용했다. 설치 완료 화면의 육안 검수·다른 OS/계정·전체 제품 회귀는 실행하지 않았다. 이전1.0.1의 WU 통과를 새1.0.2의 회귀 통과로 사용하지 않는다.

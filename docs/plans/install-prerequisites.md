# Setup 구성품 자동 준비 계획

**Goal:** 다른 PC에 Setup 하나로 OCR·승인 Baseline과 설정을 준비한다.
**Architecture:** VXvue의 설치 후 준비 명령을 Bellalun에 맞춰 적용한다. 기존 GUI 첫 실행 탐지와 자료 묶음을 재사용한다. DB 복원은 실행하지 않는다.
**Tech Stack:** Python, Nuitka standalone, Inno Setup 6.7.3.
**Spec:** SPEC.md REQ-DIST-007, REQ-DIST-001/003/006.

## 범위와 재사용

- VXvue `packaging/components.json`, `core/prereqs.py`, `packaging/installer.iss`를 조사했다. 고정 OCR 설치 파일·해시와 준비 결과 표시 방식을 재사용한다.
- Bellalun `resources.py`, `runtime.py`, GUI 첫 실행 탐지, 기존 approved-assets를 확장한다. 제품별 DB recipe는 가져오지 않는다.
- 사용자 요청에 따라 Setup에 오프라인 설치 파일을 넣는다. 런타임 다운로드는 하지 않는다. 정상 OCR은 재사용, 누락·실행 실패면 포함된 설치 파일 실행, 명시한 사용자 경로가 잘못됐으면 보존하고 안내한다.

## 작업

- [x] 격리 시험: 정상/누락/변조/실행 실패/시간 초과/설정 보존/자료 검증의 실패를 확인한다.
- [x] `prerequisites.py`에 해시 검사·OCR 준비·설정 연결·요약 저장을 구현하고 CLI에 연결한다.
- [x] 빌드가 검증한 OCR 파일을 포함하고 Inno가 준비 종료를 기다려 결과를 표시한다.
- [x] 단위·정적·준비 검사, 코드 검토, 문서 갱신 후 커밋·푸시한다.
- [x] 새 후보 Setup을 실제 컴파일하고 구성품 준비를 검증한다. 전체 제품 회귀는 실행하지 않는다.

실행 결과와 남은 범위는 [검증 기록](../setup-preparation-validation.md)을 따른다. 실제 clean PC 누락OCR 설치는 이번 환경에서 확인하지 못했다.

## 검증과 위험

실제 clean PC는 없으므로 누락 OCR 설치 경로는 격리 시험으로 검증한다. 실제 다른PC 설치는 남은 검증 범위로 기록한다. 기존 공용 OCR은 제거하지 않는다. 빌드 다운로드는 공식 release digest와 대조한다. 기존 설정·결과와 사용자 DB는 보존한다.

## 후속 요청: 배포 폴더 정리

- [x] REQ-DIST-003에 `release/<버전>/` 최종 배포·동일 버전 덮어쓰기 중단·Git 제외를 정의한다.
- [x] 배포 이동과 기존 폴더 충돌의 실패 시험 후 빌드 게시 단계를 구현한다.
- [x] 현재1.0.2 파일5개를 이동하고 구버전18개 폴더를 제거한다. 빌드 기록과 실행 증거는 별도 보존한다.

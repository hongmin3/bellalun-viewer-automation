# 다른 PC 실행 이식성 점검 결과

## 수정 완료

- 실행 전 Primary display를 1920x1080으로 설정하고 실제 결과를 검증한다.
- DPI를 Per-Monitor V2로 인식하며 100%(96 DPI)가 아니면 UI 조작 전에 중단한다.
- 관리자 권한과 Viewer/XIPL/Parameter/Tesseract 경로를 사전 검사한다.
- Viewer 조작은 MFC Control ID와 실제 Control rectangle을 기본으로 사용한다.
- XIPL TC01은 최대화하지 않고, 창 위치/크기와 무관한 창 내부 비율로 Overlay를 OCR한다.
- XIPL 영상 로딩은 고정 sleep 대신 최초 유효 2304x3072/W1/W2 프레임을 기다린다.
- XIPL 메뉴와 PIM 패널은 WPF UI Automation을 우선 사용한다.
- PIM 패널의 저장 위치가 화면 밖이면 TransformPattern으로 현재 XIPL 창 안에 이동한다.
- DICOM 서버/검증 목록의 화면 판별을 절대 좌표에서 Viewer 창 상대 비율로 변경했다.
- Procedure + 팝업 좌표는 팝업 실제 크기에 대한 비율로 변경했다.
- XIPL Parameter 디렉터리와 실행 경로를 config.json으로 분리했다.
- Parameter 목록 순서를 가정하지 않고 선택 후 이름을 검증한다.
- 2D/3D 처리 대기값을 config.json에서 PC 성능에 맞게 조절할 수 있다.

## 확인된 제한

- Bellalun 제품 버전이나 UI 언어가 달라 Control ID 자체가 변경되면 새 Control map이 필요하다.
- Windows 배율은 안전하게 즉시 강제 변경할 수 없으므로 100%가 아니면 중단한다.
- 1920x1080 모드를 디스플레이 드라이버가 지원하지 않으면 해상도를 변경하지 않고 중단한다.
- MWL/Storage/Print 연결은 대상 PC의 NIC, 방화벽, 서버 접근 가능 여부에 의존한다.
- 시험 환자 DATA_FLOW_MWL_01과 InstanceType 0/1/2/3 데이터가 대상 DB에 있어야 한다.
- TC03은 자동화가 정상 수행되지만 Apply 후 재진입 시 3D 값이 기본값으로 복귀하여 실제 FAIL이다.

## 검증 명령

```powershell
python run.py portability-check
python run.py run-xipl-01
python run.py run-xipl
```

# Bellalun Viewer 기본기능 자동화

관리자 권한의 명령 프롬프트에서 실행한다. Codex나 Claude 연결은 필요 없다.
Viewer를 미리 실행할 필요는 없다. 각 UI 명령은 첫 클릭 전에 Viewer를 직접
실행하고 로그인·DB 연결·Patient 화면·전면 활성화를 확인한다.

처음 복제한 PC에서는 `config.example.json`을 `config.json`으로 복사하고 Viewer
계정, 설치 경로, DICOM 서버 주소를 입력한다. `config.json`은 로그인 정보와
시험망 주소를 포함할 수 있어 Git에서 제외된다.

## 실행

- 전체 안전 자동화: `run_all.cmd`
- Print 서버 등록만: `setup_print.cmd`
- DICOM 전체 등록: `python run.py setup-dicom`
- Storage 서버/옵션만: `python run.py setup-storage`
- WorkFlow_01 MWL+Local 9단계: `python run.py run-wf01`
- Local 검사 + F8 Demo 촬영: `python run.py run-ui`
- XIPL 01~03 실제 UI 시험: `python run.py run-xipl`
- XIPL 표시값 비교(TC01)만: `python run.py run-xipl-01`
- 3D Post Reconstruction만 재시험: `python run.py run-xipl-03`
- 다른 PC 실행환경 점검: `python run.py portability-check`
- 자동화 범위 확인: `python run.py list`

`run-auto`는 설치/환경 정적 점검, MWL·Storage·Print 등록과 Echo, Local 검사 생성,
F8 Demo 촬영, Viewer 내부 2D/3D 영상 처리 및 DB 판정을 순서대로 수행한다. 실제 X-ray, Gantry, Detector,
팬텀 촬영, OS 설치/삭제는 수행하지 않는다.

## 결과

`Reports/Result_YYYYMMDD_HHMMSS.{html,csv,json,txt}`에 TC별
`PASS/FAIL/MANUAL/SKIP`과 Expected/Actual 결과가 저장된다. 실패 시 프로세스는
종료 코드 1을 반환하므로 배치/CI에서도 성공 여부를 판정할 수 있다.

## DICOM 설정

- MWL: `MWL_TEST / MWL_SCP / 10.13.0.222:11112`
- Storage: `BUNNY_TEST / Bunny / 10.201.0.139:3000`
- Print: `PRINT_TEST / PRINT_SCP / 10.13.0.222:11113`

Bunny는 반드시 설치 폴더를 작업 디렉터리로 실행하며 Storage Server 노드를
활성화한다. Storage의 Use는 BUNNY_TEST 하나만 남긴다. Burn Option의
Annotation/Label/Information과 Image Option의 Apply preview position을 체크하고
Dose SR은 Send로 설정한다. 서버 정보와 옵션이 이미 같으면 재입력/Update 없이
Echo만 다시 수행한다. Echo는 결과 6단계 이상과 `Connected Fail` 없음으로 판정한다.
Print Overlay는 별도 후속 자동화 범위이며 현재 `setup-dicom`에서는 변경하지 않는다.

`run-wf01`은 시작 전에 MWL DB 설정(Use 포함)과 TCP를 확인한다. 미등록/불일치이면
검색을 시도하지 않고 명확한 FAIL을 출력한다. Viewer가 MWL 오류 팝업을 표시하면
화면을 증적으로 저장하고 OK로 닫은 뒤 안전하게 중단한다.

## F8 Demo 촬영

촬영 화면에서 Step을 선택하고 Ready 배너를 확인한 뒤 F8을 누른다. 생성된
INSTANCE 수, 영상 그룹, Series/SOP Instance UID, Dose 정보를 DB에서 대조한다.
Demo 영상 내용 자체는 선택한 View Position과 연관되지 않으므로 화질·해부학적
적합성은 자동 PASS로 판정하지 않는다.

## XIPL

`run-xipl`은 `DATA_FLOW_MWL_01` 완료 검사를 View 화면에서 Patient ID로 찾아 연다.
이 fixture는 빈 MWL 검사에서 Procedure `+`로 LCC(2D) 1개와 LCC(3D-N) 1개만
등록하고 F8로 획득한 데이터다. XIPL은 반드시 Viewer Tools의 XIPL(ID 1160)로
호출하고, 2D는 Process Control(ID 1151), 3D는 `<<`를 펼친 뒤 Post
Reconstruction(ID 1178)으로 진입한다.

원본 Parameter는 수정하지 않고 `TEST_2D_FLOW.pim`과 `TEST_3D_FLOW.xtp`
복사본만 사용한다. 2D의 Contrast/Sharpness/Brightness/Tone/Noise 전 항목과,
3D Recon·Syn의 Background Masking/Contrast/Sharpness/Brightness/Tone 전 항목을
크게 변경한다. Recon과 Syn의 Tone은 기본/최대값이 20이므로 모두 감소시킨다.
Preview, Apply, 재진입 후 Parameter 유지까지 자동으로 판정한다.

TC01은 XIPL을 최대화하지 않는다. Viewer에서 XIPL을 호출한 뒤 영상 로딩 진행창이
사라지고 2304x3072/W1/W2가 처음 표시되는 프레임을 즉시 읽는다. XIPL 창의 저장
위치와 크기는 PC마다 달라도 창 자체 좌표계로 OCR하며, PIM 패널이 이전 모니터
좌표를 기억해 화면 밖에 열리면 Windows UI Automation으로 현재 창 안에 이동한다.

## 다른 PC에서 실행

모든 UI 명령은 실행 전에 Primary display를 1920x1080으로 설정하고 다음 조건을
검사한다. 하나라도 맞지 않으면 첫 UI 클릭 전에 FAIL로 중단한다.

- 관리자 권한 Python
- Primary display 1920x1080
- Windows 배율 100%(96 DPI)
- Viewer, XIPL Studio, XIPL Parameter, Tesseract 경로 존재

설치 경로가 다른 PC는 `config.json`의 `viewer.exe`, `xipl.studio_exe`,
`xipl.parameter_dir`, `xipl.tesseract_exe`, `data_dir`를 변경한다. 추가 Parameter가
있어 목록 순서가 달라도 TEST_2D/TEST_3D 이름을 실제로 읽어 선택한다.

컨트롤 ID는 해상도가 아니라 Bellalun 버전/화면 언어에 종속된다. 현재 기준은
Bellalun 1.0.12 계열, English UI다. 다른 제품 버전에서는 존재하지 않는 ID를
임의 클릭하지 않고 해당 단계에서 중단하도록 구성되어 있다.

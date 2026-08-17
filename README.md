# Bellalun Viewer 기본기능 자동화

관리자 권한의 명령 프롬프트에서 실행한다. Codex나 Claude 연결은 필요 없다.
Viewer를 미리 실행할 필요는 없다. 각 UI 명령은 첫 클릭 전에 Viewer를 직접
실행하고 로그인·DB 연결·Patient 화면·전면 활성화를 확인한다.

처음 복제한 PC에서는 `config.example.json`을 `config.json`으로 복사하고 Viewer
계정, 설치 경로, DICOM 서버 주소를 입력한다. `config.json`은 로그인 정보와
시험망 주소를 포함할 수 있어 Git에서 제외된다.

**실행 중 마우스/키보드 점유**: Bellalun Viewer의 버튼 대부분이 커스텀 렌더링
컨트롤이라 표준 Windows 메시지에 반응하지 않아, 이 자동화는 실제 물리적
마우스 커서(`SetCursorPos`+`mouse_event`)와 키보드 입력(`SendInput`)을 사용한다.
실행 중에는 같은 Windows 세션에서 다른 작업을 하기 어려우므로, 자동화를 돌리는
동안 PC를 함께 써야 한다면 Switch User로 별도 세션을 만들어 그 안에서 실행한다
(자세한 준비사항은 `..\지식\[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md` 5절 참고).

## 실행

- 초기 상태 전체 회귀: `run_all.cmd` 또는 `python run.py run-regression`
- Print 서버 등록만: `setup_print.cmd`
- DICOM 전체 등록: `python run.py setup-dicom`
- Storage 서버/옵션만: `python run.py setup-storage`
- WorkFlow_01 MWL+Local 9단계: `python run.py run-wf01`
- WorkFlow_02 2D/3D Demo 촬영 및 Tool 적용: `python run.py run-wf02`
- WorkFlow_03 DICOM Print Overlay·실제 출력·웹 프리뷰 검증: `python run.py run-wf03`
- Local 검사 + F8 Demo 촬영: `python run.py run-ui`
- XIPL 01~06 실제 UI 시험: `python run.py run-xipl`
- XIPL 표시값 비교(TC01)만: `python run.py run-xipl-01`
- 2D Image Processing(TC02)만: `python run.py run-xipl-02`
- 3D Post Reconstruction만 재시험: `python run.py run-xipl-03`
- Preset별 2D Default Parameter(TC04)만: `python run.py run-xipl-04`
- Q.C Default Image Process Parameter(TC05)만: `python run.py run-xipl-05`
- XIPL Parameter 저장 후 Viewer 적용(TC06)만: `python run.py run-xipl-06`
- System 연동 3D-Narrow/3D-Wide 촬영(TC_System_compatibility_03/04):
  `python run.py run-sys3d`
- 다른 PC 실행환경 점검: `python run.py portability-check`
- 자동화 범위 확인: `python run.py list`

`run-auto`는 설치/환경 정적 점검, MWL·Storage·Print 등록과 Echo, Local 검사 생성,
F8 Demo 촬영, Viewer 내부 2D/3D 영상 처리 및 DB 판정을 순서대로 수행한다. 실제 X-ray, Gantry, Detector,
팬텀 촬영, OS 설치/삭제는 수행하지 않는다.

`run-regression`은 Examined 영상 데이터가 없는 초기 상태를 기준으로 Install 01/02 정적
점검, DICOM 서버 설정, WorkFlow_01 fixture 생성, WorkFlow_02 2D/3D 데이터 생성,
WorkFlow_03 실제 DICOM Print, **XIPL_01을 포함한 XIPL 01~06**을 의존 순서대로
실행한다. XIPL_02는 변경 전후 파라미터, Preview 화면 변화,
Viewer 처리 로그, ImageAction 결과 파일과 재진입 값을 교차 검증한다. XIPL_03은 창이
닫힌 사실만으로 PASS하지 않고 10개 파라미터의 실제 변경, xtp 전달 로그, Apply 후 재진입
표시값을 판정한다. 10개 값 유지는 GPU 유무와 관계없이 필수이며 기본값으로 복귀하면
FAIL이다. GPU가 있는 환경에서는 Recon/Syn DB·파일 변화도 필수다. GPU 미탑재로
`No GPUS`만 발생하면 결과 생성 검증만 SKIP으로 분리하며, GPU 유무 판단은 실제로
초기화를 시도하는 Preview 단계의 로그를 기준으로 한다(Apply는 재초기화를 하지 않아
오류 자체를 남기지 않기 때문). 이 GPU-없음 SKIP 규칙은 XIPL_03뿐 아니라 앞으로 추가될
3D/Reconstruction 계열 TC에도 동일하게 적용한다.
`release_note._source`가 교체 필요 상태이거나 `REPLACE_ME`가 남아 있으면 임시 버전과
설치 버전을 비교해 FAIL로 만들지 않고, 현재 실제 버전을 수집한 뒤 Install_01을 MANUAL로
보고한다. 승인된 Release Note 기준을 입력한 경우에만 자동 PASS/FAIL 비교를 수행한다.

### XIPL 픽스처(Fixture) 신선도

`open_test_study()`는 `DATA_FLOW_MWL_01`의 InstanceType 0/1/2/3이 모두 있는
**가장 최근** Study를 연다. Viewer의 View 검색 화면 기본 기간 필터가 "Today"라서,
며칠 지난 픽스처를 그대로 열려고 하면 검색 자체가 0건이 된다. 이를 막기 위해
`run-xipl-01`/`02`/`03`을 단독 실행할 때는 시작 전에 오늘 날짜의 InstanceType
0/1/2/3 픽스처가 있는지 확인하고, 없으면 WF01(MWL 처방 삭제 후 재등록 + Local
보류 검사 생성)과 WF02(Demo F8 2D/3D 촬영)를 먼저 자동 실행해 오늘 날짜 픽스처를
새로 만든 뒤 진행한다. `run-regression`은 WF01→WF02를 이미 거치므로 이 재생성이
다시 일어나지 않는다. MWL 서버에서 지우는 대상은 항상 이 자동화가 사용하는
patient_id로 한정하며, MWL 서버 전체 삭제(`delete-all`)는 사용하지 않는다.

## 결과

`Reports/Result_YYYYMMDD_HHMMSS.{html,csv,json,txt}`에 TC별
`PASS/FAIL/MANUAL/SKIP`과 Expected/Actual 결과가 저장된다. 실패 시 프로세스는
종료 코드 1을 반환하므로 배치/CI에서도 성공 여부를 판정할 수 있다. JSON에는 TC
전체 `duration_seconds`와 함께 `timings` 배열이 들어있어 Step별 소요시간, 상태
기반 대기(`wait`)의 이름·시작/종료 시각·소요시간·종료 원인(`control appeared`,
`log/control completion detected`, `timeout` 등)·세부 detail을 그대로 확인할 수
있다. 실행 시간을 재려면:

```powershell
$sw=[Diagnostics.Stopwatch]::StartNew()
python run.py --config config.json run-regression
$code=$LASTEXITCODE
$sw.Stop()
"ELAPSED_SECONDS=$([math]::Round($sw.Elapsed.TotalSeconds,3))"
```

2026-08-11 최적화(고정 sleep 제거 → 상태 기반 대기) 전 전체 회귀는 1290.6초였고,
2026-08-14 실측 전체 회귀는 895초로 약 396초(30.7%) 단축되었다.

### PASS/FAIL 판정 근거를 신뢰하는 방법

자동 판정 결과를 눈으로 재구성할 수 있도록, 모든 TC의 모든 Check는 리포트에
`Expected`/`Actual` 실제값을 남기고 애매한 판정에는 `note`로 비교 근거(어떤
로그 문구, DB 컬럼, 재진입 시 UI 값, 파일 해시/시각을 대조했는지)를 밝힌다. 이
정책은 기존 TC뿐 아니라 앞으로 추가할 TC에도 동일하게 적용한다(자세한 규칙은
`..\지식\[자동화 운영 지침] Bellalun Viewer auto 저장소 구현 규칙.md` 2절 참고).

주요 Workflow/XIPL은 UI 플로우가 끝났다는 사실만으로 PASS하지 않는다.

- WorkFlow_01: MWL 원본 응답과 Viewer 표시 환자정보, Study UID, 보류/Local Study DB 값을 대조한다.
- WorkFlow_02: 새 Study의 InstanceType 0/1/2/3, Series/Group/UID 구조, Tool 전후 OCR·화면 변화, 완료 DB 상태를 대조한다.
- WorkFlow_03: Print Overlay DB 항목/서버 매핑, Film 1×1 표시 실제값, 신규 Print job, 웹 preview 실제값과 raster를 대조한다.
- XIPL_01: 같은 Instance의 Viewer–XIPL W1/W2와 실제 PIM 파일명을 대조한다.
- XIPL_02: 원본 XML, 변경한 5개 UI 값, Preview 변화, 처리 로그/파일, Apply 후 재진입 5개 값을 대조한다.
- XIPL_03: 변경한 Recon/Syn 10개 값, Preview 처리 로그, Apply의 실제 신규 완료 로그(타임스탬프
  필터링으로 이전 동작의 지연 로그와 구분), Apply 후 재진입 10개 값을 대조한다. 재진입 시
  기본값 복귀는 GPU 유무와 무관하게 FAIL이다.

## DICOM 설정

- MWL: `MWL_TEST / MWL_SCP / 10.13.0.222:11112`
- Storage: `BUNNY_TEST / Bunny / 127.0.0.1:3000` (Bunny가 Viewer와 같은 로컬 PC에서 동작하는 환경 기준)
- Print: `PRINT_TEST / PRINT_SCP / 10.13.0.222:11113`

Bunny는 반드시 설치 폴더를 작업 디렉터리로 실행하며 Storage Server 노드를
활성화한다. Storage의 Use는 BUNNY_TEST 하나만 남긴다. Burn Option의
Annotation/Label/Information과 Image Option의 Apply preview position을 체크하고
Dose SR은 Send로 설정한다. 서버 정보와 옵션이 이미 같으면 재입력/Update 없이
Echo만 다시 수행한다. Echo는 결과 6단계 이상과 `Connected Fail` 없음으로 판정한다.
`run-wf03`은 Setting > DICOM > Print Overlay에서 `TC_WF03_OVERLAY`를 만들고 Patient ID,
Birth Date, Thickness, Compression Force, HVL, AGD 여섯 항목을 Top에 등록한다. 이어서
Setting > DICOM > Print의 `PRINT_TEST`에 해당 Overlay를 선택해 저장하고 DB Key를 대조한다.
Display Overlay는 변경하지 않는다. Film은 2×2 기본 상태에서 Control ID 1141로 1×1로
전환한 후 실제 Print를 수행한다. Print 서버의 신규 job만 식별하여 웹 Viewer가 사용하는
preview 원본에서 여섯 실제값을 OCR하고, Film과 서버 raster 유사도(기준 0.96)를 비교한다.

`run-wf01`은 시작 전에 MWL DB 설정(Use 포함)과 TCP를 확인한다. 미등록/불일치이면
검색을 시도하지 않고 명확한 FAIL을 출력한다. Viewer가 MWL 오류 팝업을 표시하면
화면을 증적으로 저장하고 OK로 닫은 뒤 안전하게 중단한다.

## F8 Demo 촬영

촬영 화면에서 Step을 선택하고 Ready 배너를 확인한 뒤 F8을 누른다. 생성된
INSTANCE 수, 영상 그룹, Series/SOP Instance UID, Dose 정보를 DB에서 대조한다.
Demo 영상 내용 자체는 선택한 View Position과 연관되지 않으므로 화질·해부학적
적합성은 자동 PASS로 판정하지 않는다.

`run-wf02`는 최신 `DATA_FLOW_MWL_01` 보류 검사 중 영상이 없는 검사만 연다. 2D LCC와
3D-N LCC를 창 상대 위치로 등록하고 Demo F8 촬영 후 `INSTANCE.InstanceType` 0/1/2/3
(2D/Raw/Recon/Syn)을 확인한다. 2D와 3D Recon에 W/L, Zoom, Pan, Arrow Annotation을
컨트롤 ID로 적용하고 단계별 화면 변화량과 PNG 증적을 저장한다. `viewer.demo_mode=true`가
아니면 실제 X-ray 노출을 피하기 위해 촬영 전에 FAIL로 중단한다.

## XIPL

`run-xipl`은 `DATA_FLOW_MWL_01` 완료 검사를 View 화면에서 Patient ID로 찾아 연다.
이 fixture는 빈 MWL 검사에서 Procedure `+`로 LCC(2D) 1개와 LCC(3D-N) 1개만
등록하고 F8로 획득한 데이터다. XIPL은 반드시 Viewer Tools의 XIPL(ID 1160)로
호출하고, 2D는 Process Control(ID 1151), 3D는 `<<`를 펼친 뒤 Post
Reconstruction(ID 1178)으로 진입한다.

원본 Parameter는 수정하지 않고 `TEST_2D_FLOW_M.pim`과 `TEST_3D_FLOW.xtp`
복사본만 사용한다. 2D의 Contrast/Sharpness/Brightness/Tone/Noise 전 항목과,
3D Recon·Syn의 Background Masking/Contrast/Sharpness/Brightness/Tone 전 항목을
크게 변경한다. Recon과 Syn의 Tone은 기본/최대값이 20이므로 모두 감소시킨다.
Preview, Apply, 재진입 후 Parameter 유지까지 자동으로 판정한다.

3D Post Reconstruction은 Preview 화면에 비교 영상이 표시되더라도 10개 UI 값 변경과
`TEST_3D_FLOW.xtp` 전달 로그(Preview 단계에서 확인)가 맞아야 파라미터 검증을
PASS한다. Apply는 Preview와 달리 `Initialize Reconstruction` 로그를 다시 남기지
않으므로(실측 확인, 2026-08-14), Apply의 완료 판정은 Apply 자체가 새로 여는
Post Recon 스레드의 종료 로그로 확인한다. 이때 로그 오프셋만으로 "이후 발생"을
판단하면 이전 동작(Preview)의 지연된 스레드 종료 로그를 Apply 완료로 오인할 수
있어(버퍼링된 로그 flush 지연으로 실제 재현됨), 각 로그 줄 자체의 타임스탬프를
Apply 클릭 시각과 비교해 필터링한다. Apply 후에는 Post Reconstruction을 다시 열어
이름과 10개 값을 전부 다시 읽는다. 변경값 유지는 GPU 유무와 관계없이 요구하며
기본값 복귀는 FAIL이다. GPU가 있는 환경에서는 해당 Study의 InstanceType 2/3 결과
파일 해시·수정 시간 변화도 요구한다. GPU 유무는 Apply가 아니라 실제로 초기화를
시도하는 **Preview 단계의 로그**로 판단하며, 그 결과가 정확히 `No GPUS`뿐이면
결과 생성만 SKIP한다. 그 밖의 Recon 오류는 FAIL이다.

TC01은 XIPL을 최대화하지 않는다. Viewer에서 XIPL을 호출한 뒤 영상 로딩 진행창이
사라지고 2304x3072/W1/W2가 처음 표시되는 프레임을 즉시 읽는다. XIPL 창의 저장
위치와 크기는 PC마다 달라도 창 자체 좌표계로 OCR하며, PIM 패널이 이전 모니터
좌표를 기억해 화면 밖에 열리면 Windows UI Automation으로 현재 창 안에 이동한다.

TC06은 XIPL Studio에서 Contrast를 15로 바꿔 `TEST_XIPL_SAVED_M.pim`으로 저장한 뒤
Viewer Image Processing에서 그 Parameter를 다시 선택해 5개 표시값을 읽고, Apply
후 재진입 표시값까지 비교한다. Viewer는 Parameter를 **선택하는 순간**
`Image Process Param Name:<file>, Contrast: ...` 로그를 남기고 **Apply는 이
로그를 다시 남기지 않는다**(창을 닫고 ImageAction 결과 파일만 쓴다, 실측 확인).
그래서 파일명·값 로그 증거는 선택 구간에서 확보하고, Apply의 완료 판정은 창 닫힘과
ImageAction 결과 파일 생성으로 한다. TC02가 Apply 전에 Preview를 눌러 같은 로그를
만드는 것과 다른 점이니 두 TC의 판정 근거를 섞지 않는다.

## System 연동 3D 촬영 (3D-Narrow / 3D-Wide)

`run-sys3d`는 `TC_System_compatibility_03`(3D-Narrow)과
`TC_System_compatibility_04`(3D-Wide)를 실행한다. 임시 Local 환자로 검사를 시작해
Procedure `+`에서 해당 Preset 탭의 LCC를 등록하고, Demo F8로 1회 촬영한 뒤 DB로
판정한다.

Preset 탭/LCC 카드 control ID는 2D = 기본 탭·`802`, 3D-N = 탭 `2083`·`852`,
3D-W = 탭 `2084`·`902`이다(`VIEW_POSITION_MODES`). 촬영 종류는
`INSTANCE_GROUP.Type`/`ExposureMode`로 확정하며 `0/0` = 2D, `1/1` = 3D-Narrow,
`1/2` = 3D-Wide다. 이 값을 보지 않으면 3D-W TC가 3D-N 촬영으로도 통과하므로
반드시 함께 판정한다. Step 카드 라벨 OCR은 글자가 작아 `3`이 `G`/`B`로 오독되므로
보조 증거로만 쓴다.

실제 X-ray 대신 Demo(F8)를 쓰기 때문에 장비 LCD 표시와 2430 패들 연결, Step 회전
각도(3D-N -7.5~7.5도 / 3D-W -15~15도)는 자동 판정하지 않고 MANUAL로 보고한다.
그래서 두 TC의 종합 판정은 MANUAL이며, 자동 판정 가능한 등록·촬영·DB 구조 단계는
PASS/FAIL로 분리해 기록한다.

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

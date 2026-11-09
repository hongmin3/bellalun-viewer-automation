# OCR 판독과 PC별 차이 확인

프린트 설정의 카탈로그·Header 콤보·Print 서버/Overlay 선택은 같은 OCR 판독 경로를 쓴다.
한 번 캡처한 컨트롤을 기본 방식으로 읽고 필요할 때만 반전·이진화·다른 문자 배치 모드를 시도한다.
정확히 구별되지 않는 후보는 누르지 않는다. DB의 저장 값과 필름 표시 확인은 그대로 수행한다.

## 준비 점검과 실패 증거

기준 배포 OCR은 Tesseract 5.5.3이다. 정상 기존 OCR을 바꾸거나 PC별 설정을 덮어쓰지 않는다.
다른 버전은 WARN으로 안내하고 `작업/ocr-runtime.json`에 엔진·언어 파일 SHA-256을 기록한다.
버전이 같아도 해시가 다르면 같은 OCR 환경이라고 보지 않는다.
1920×1080·100%(96 DPI)와 주 모니터 기준은 유지한다.

선택 실패에는 해당 TC 증거 폴더 아래 `ocr-*` 폴더가 생긴다. 원본 크롭·전처리 크롭과
`selection.json`의 판독문·신뢰도·후보 점수·영역·OCR 지문을 함께 본다.
캡처 실패와 증거 기록 실패도 오류로 보고한다. 화면을 가린 다른 창과 원격 접속 배율부터 확인한다.
증거에는 실제 화면 내용이 있으므로 사내에서만 보관한다. 이 파일들을 공개 저장소에 넣지 않는다.

## 저장 이미지 비교

`tools/ocr_replay.py`는 Viewer 조작이나 DB 연결 없이 저장된 크롭을 같은 판독/선택 규칙으로 비교한다.
실제 문제 PC의 캡처는 다음 형식으로 manifest와 같은 폴더에 둔다.

```json
{"cases": [{"name": "Header", "wanted": "Top", "images": ["row0.png", "row1.png"], "expected": 0, "match": "exact"}]}
```

`expected`는 선택되어야 할 이미지의 0부터 시작하는 번호다. 선택하면 안 되는 경우는 `null`과
`reason`(`ambiguous` 또는 `unreadable`)을 적는다. 실제 캡처를 사람이 읽어 기대값을 정한다.

```powershell
python tools/ocr_replay.py <manifest.json> --tesseract <tesseract.exe> --output <새 결과.json>
```

종료0은 모든 사례 일치, 1은 불일치, 2는 입력 오류다. 기존 결과는 덮어쓰지 않는다.
다른 PC 자료가 없는 합성 이미지 통과는 그 PC의 제품 UI 검증을 대신하지 않는다.

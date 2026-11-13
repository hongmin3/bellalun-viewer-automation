# WF14 / XIPL03 사양 재평가

이 문서는 과거 결과의 사양 재평가이며 새 제품 실행·회귀 PASS·릴리스 gate 증거가 아니다.
원시 보고서와 과거 수행 이력을 수정하지 않았다.

원본: `work/run652-gui/runtime/Reports/Result_20261113_025023.json`.
SHA256: `4e106fa291bfe1ced820423c3c1eb6497a8f6e8b1b2fa07fe097245c5e1209b6`.

| 대상 | 원시 기록 | 사양 재평가 | 남은 확인 |
|---|---|---|---|
| WF14 | 20 PASS / 3 FAIL | PASS: Import 제외인 UPS 변경값 유지. 화면 차이는 UPS 모델 2536 한 항목과 그에 따른 파생 실패뿐 | 신규 설치판 기본기능/WU 회귀 |
| XIPL03 | 재진입한 우측 기본값을 변경값과 비교해 FAIL, 뒤 검증 중단 | 기존 기대값 오류. 우측 기본값과 영상 Overlay 적용값을 구분해야 함 | Recon/Syn 전체 결과·실제 img 저장값·재시작 실물 확인. 전체 PASS 변경 금지 |

WF14 근거는 SRS 01-10-60의 Import 표(사양서261030 물리486쪽)다. Export485쪽의 포괄
문장보다 Import의 Device 예외가 직접 기준이다. 서버 TC Setting row23 N/O와 영향평가
V1.0.5 row79 G/H/R79도 UPS 제외를 뒷받침하며 로컬 개정TC row24 Expected7에는 UPS
복원 요구가 없다. 원시 Step3 변경 후 값과 Import 후 값은 모두 `EATON El`이었다.
나머지 56페이지/508항목에서 UPS 모델 한 차이 외의 차이나 한쪽 누락은 없었다.
다른 Device 설정을 비교에서 제외하는 결론은 아니다.

XIPL03 근거는 SRS03-50-230 물리765–768쪽, Operation Manual V1.0.12W1 문단
2787/2795/2809–2810/2820, 서버TC Examine_Mode row100, 영향평가 V1.0.5 rows344–345다.
과거 Syn Overlay X/6/14/6/15와 선택 파일명 유지 증거는 있지만 잘못된 assert 이후의 DB/
파일·Recon 전체 프레임·재시작 증거는 부족하다. No GPUS 문구만으로 원인·지원 여부나
산출물 SKIP을 단정하지 않는다.

사양서 해시 `e256ddaf1423f2c97b811b385c1eb66f840f2b9370591c6e7cee1f0b2b673036`,
Operation `982bb26d6c8cac5dfeb4dbc961b14c04d063c9aeb8bc6bee329cde55ba72e223`,
서버TC `3e3cbdcebacd0689eb01d95fdcb15f80d477d485b75750466ed7517261f2593c`,
영향평가 `fba58863a4b144b225c3c3ec231a3f26fb32d9a9e4fa0713e80ce5878abf3614`.
사내 원문은 공개 저장소에 넣지 않는다. 관련 문서 교차 검토는 전체 1,089쪽 정독을 뜻하지 않는다.

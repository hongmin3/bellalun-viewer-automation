# 후보9 WU_09 USB Export 실패 조사

2026-11-06 후보9 설치판의 두 전체 회귀에서 WF_02는 통과했지만 WU_09가 실패했다. **USB IMG Export 도중 제품 프로세스의 비정상 종료가 기록됐다.** 자동화는 완료 문구와 Import 증거를 확인하지 못해 FAIL을 유지했고, 배포 게이트도 거부했다. 이 실패를 알려진 결함 허용 목록에 추가하지 않았다.

## 확인한 사실

| 시각·자료 | 관찰 |
|---|---|
| Viewer 로그 08:31:29~31 | Export Manager를 시작하고 열림 알림을 받았다. |
| ExportManager 로그 08:31:38.398 | USB 관리 폴더를 대상으로 IMG Export Start를 눌렀다. |
| ExportManager 로그 08:31:38.694 | 상태가 Ready에서 Exporting으로 바뀌었다. |
| ExportManager 로그 마지막 08:31:53.161 | 영상 파일 Export 기록 이후 로그가 끊겼다. 완료·정상 종료 기록은 없다. |
| Windows Application Error, Event 1000, 08:31:53.397 | `EXPORT.MANAGER.exe`, 버전 `1.0.12.105`, 모듈 `ntdll.dll` 버전 `10.0.26100.9818`, 예외 `c0000374`, 프로세스 `0x6b8` 기록. |
| Windows Error Reporting, Event 1001, 08:31:56.794 | 같은 Export Manager 오류 보고가 기록됐다. |
| USB 폴더 읽기 전용 확인 | IMG 3개와 부가 TXT 3개가 있다. 파일 존재만으로 Export 완료나 Import 성공을 판정하지 않는다. |
| WU 보고서 | `USB Export/Import: ExportManagerError: Export Manager 창을 유일하게 식별하지 못했습니다. (문구='', 증거=None)` |

자동화의 `core/export_manager.wait_export_completion`은 살아 있는 대상 프로세스에서 경로 Edit를 가진 유일한 창을 확인하고, 실제 성공 문구·증거 저장·확인 후 종료를 요구한다. 이번에는 그 창을 식별하지 못한 뒤 제품 충돌 기록이 확인됐다. 이 메시지 자체를 창 대기 상한 부족이나 자동화 오판으로 확정하지 않는다. Export 준비/파일 처리/환경/자동화 입력 중 무엇이 충돌을 유발했는지와 재현 빈도는 아직 미확정이다.

## 결과와 다음 범위

- 후보9 기본기능: PASS23 / FAIL2 / MANUAL1 / SKIP1, 122.9분. WF_02의 3D-N/W와 후속 Tool·종료가 모두 통과했다. FAIL2건은 기존 허용 제품 결함이다.
- 후보9 WU: PASS9 / FAIL1(`WU_09`) / SKIP3, 106.4분. 나머지 체인은 끝까지 실행했다.
- 배포 게이트: 26개 중25개 통과, 거부1건은 WU_09다. 후보9를 배포 통과로 표시하지 않는다.
- 승인된 두 전체1회는 끝났다. 추가 USB 단독 실환경 진단은 승인 후 실행한다. 기존 검사·USB 관리 폴더를 사용하고 DB 복원 없이 제품 충돌 자료·UI 상태를 함께 수집하는 범위를 우선 제안한다. 제품 패치·PC 재부팅·드라이버 변경을 임의 수행하지 않는다.

원본 보고서·각 실행 직후 보존한 스냅샷·해시·게이트 결과·관련 이벤트 요약은 Git 제외 실행 기록과 `work/candidate9-regression/`에 보존한다. WU 보고서의 TC 집계 시각은08:40:46이며, 실제 USB Export 사건 시각은 위 제품·Windows 로그를 기준으로 구분한다. 사건 근거 수집을 수정 완료·재현 완료·제품 적합 판정으로 바꾸지 않는다.

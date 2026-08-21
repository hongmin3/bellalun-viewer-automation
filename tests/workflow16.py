# -*- coding: utf-8 -*-
r"""TC_Basic_WorkFlow_16 — Kiosk 및 System Launcher.

기준 문서: ``..\Bellalun_Viewer_기본기능_Checklist_개정본.xlsx`` 시트 ``개정 TC``.

2026-08-21 사용자 지시로 이 TC 전체를 수동 수행한다. 자동화 코드는 두지 않고,
회귀 보고서와 체크리스트에서 TC가 빠지지 않도록 MANUAL 한 건만 기록한다.

수동 사유
  * Step 3은 시스템 재시작, Step 12는 PC 종료라 자동화 세션이 함께 종료된다.
  * Step 4~9의 System Launcher는 재시작 후 Kiosk 조건에서만 나타난다.
  * Step 5/6의 VIVIX-M Setup / Bellalun System Setup은 이 PC에 설치되어 있지 않다.
  * Kiosk를 Use로 둔 채 재부팅하면 Windows 바탕화면이 나오지 않아 복구 위험이 있다.
"""

from core.result import TCResult


def run(ctx):
    """제품 UI를 열거나 설정을 변경하지 않고 사용자 지정 수동 판정만 기록한다."""
    del ctx
    result = TCResult("TC_Basic_WorkFlow_16", "Kiosk 및 System Launcher")
    result.manual(
        0,
        "이 TC 는 사용자가 수동으로 동작 확인한다",
        "**사용자 지정 수동 TC (2026-08-21).** 자동화 코드를 구현하지 않고 제품 UI도 "
        "조작하지 않는다. 사유: Step 3(시스템 재시작)과 Step 12(PC 종료)는 자동화 "
        "세션을 함께 종료시키고, Step 4~9의 System Launcher는 재시작 후 Kiosk "
        "조건에서만 나타난다. Step 5/6의 VIVIX-M Setup / Bellalun System Setup은 "
        "엔지니어 전용 프로그램으로 이 PC에 설치되어 있지 않다. **수행 방법**: "
        "개정본 Step 1~12를 시험자가 순서대로 직접 수행하고 결과를 체크리스트에 "
        "기록한다. **주의**: Kiosk를 Use로 둔 채 재부팅하면 Windows 바탕화면이 "
        "나오지 않는다. 시험 후 반드시 Not Use로 되돌린다. **해제 조건**: 없음 "
        "(자동화 재시도 대상이 아님).",
        expected="시험자가 개정본 Step 1~12 를 수동 수행",
        actual="자동화 미수행 (사용자 지정 수동)",
    )
    return result

# -*- coding: utf-8 -*-
"""영향 기반 선택 회귀(`run-regression --select`)의 선택 해석. SPEC REQ-SPEEDUP-002.

선택한 TC에 smoke·전제·선행 TC를 더해 기본 전체와 같은 체크리스트 순서로 돌려준다.
제품을 조작하지 않으므로 Context 생성 전에 입력을 거부할 수 있다.
"""
import re

#: 기본 전체 사슬의 단계 ID(`run._basic_chain_stages`와 같은 순서). 기준 상태 복원은 사슬 밖 첫 단계다.
BASIC_CHAIN_IDS = (
    "TC_Basic_Install_01", "TC_Basic_Install_02", "DICOM_Server_Setup",
    *(f"TC_Basic_WorkFlow_{i:02}" for i in range(1, 17)),
    "TC_XIPL_compatibility",
)
#: 언제나 실행하는 전제(전제 게이트, `run-regression`의 PRECONDITIONS).
PRECONDITIONS = ("DICOM_Server_Setup",)
#: 언제나 실행하는 짧은 smoke.
SMOKE = ("TC_Basic_Install_02", "TC_Basic_WorkFlow_01")
XIPL_STAGE = "TC_XIPL_compatibility"

_FIXTURE = ("TC_Basic_WorkFlow_01", "TC_Basic_WorkFlow_02")
_OVERLAY = ("TC_Basic_WorkFlow_03",)


def dependencies(stage_id):
    """선행 TC. WF_03~15·XIPL은 WF_01·02가 만든 DATA_FLOW_MWL_01을, WF_08·14·15는 WF_03의 Overlay를 쓴다.

    WF_14는 Step 7에서 Print Overlay 목록 행을 열거한다. 기준 상태에는 그 행이 없다.
    """
    if stage_id == XIPL_STAGE:
        return _FIXTURE
    match = re.fullmatch(r"TC_Basic_WorkFlow_(\d\d)", stage_id)
    if not match:
        return ()
    number = int(match.group(1))
    if number in (8, 14, 15):
        return _FIXTURE + _OVERLAY
    if 3 <= number <= 15:
        return _FIXTURE
    if number == 2:
        return ("TC_Basic_WorkFlow_01",)
    return ()


def normalize(name):
    """정식 ID나 짧은 이름(`wf08`, `install02`, `xipl`, `xipl-04`)을 사슬 단계 ID로 바꾼다."""
    text = str(name or "").strip()
    if text in BASIC_CHAIN_IDS:
        return text
    if re.fullmatch(r"TC_XIPL_compatibility_0[1-7]", text):
        return XIPL_STAGE
    key = re.sub(r"[\s_-]", "", text.lower())
    match = re.fullmatch(r"wf(\d{1,2})", key)
    if match and 1 <= int(match.group(1)) <= 16:
        return f"TC_Basic_WorkFlow_{int(match.group(1)):02}"
    match = re.fullmatch(r"install(\d{1,2})", key)
    if match and f"TC_Basic_Install_{int(match.group(1)):02}" in BASIC_CHAIN_IDS:
        return f"TC_Basic_Install_{int(match.group(1)):02}"
    if re.fullmatch(r"xipl(0?[1-7])?", key):
        return XIPL_STAGE
    if key in {"dicom", "dicomserversetup"}:
        return "DICOM_Server_Setup"
    raise ValueError(f"선택 회귀에서 알 수 없는 TC입니다: {text or '(빈 값)'}")


def resolve(requested, chain_ids=BASIC_CHAIN_IDS):
    """요청 TC → {requested, dependencies, smoke, executed}. 순서는 모두 체크리스트 순서다."""
    order = {stage_id: index for index, stage_id in enumerate(chain_ids)}
    picked = {normalize(name) for name in requested if str(name or "").strip()}
    if not picked:
        raise ValueError("선택 회귀에 실행할 TC를 하나 이상 지정하세요.")
    unknown = sorted(picked - set(order))
    if unknown:
        raise ValueError(f"기본 사슬에 없는 단계입니다: {', '.join(unknown)}")
    needed = set(picked) | set(SMOKE) | set(PRECONDITIONS)
    pending = list(needed)
    while pending:
        for dependency in dependencies(pending.pop()):
            if dependency not in needed:
                needed.add(dependency)
                pending.append(dependency)
    executed = sorted(needed, key=order.__getitem__)
    if set(executed) == set(chain_ids):
        raise ValueError("선택 결과가 기본 전체와 같습니다. 전체 회귀는 run-regression(--select 없이)으로 실행하세요.")
    ordered = lambda ids: sorted(ids, key=order.__getitem__)
    return {"requested": ordered(picked),
            "dependencies": ordered(needed - picked - set(SMOKE) - set(PRECONDITIONS)),
            "smoke": ordered(set(SMOKE) - picked),
            "executed": executed}


def scope_of_arguments(arguments):
    """명령 인수에 `--select`가 있으면 'selected'. 완료 리포트를 찾을 범위를 정한다."""
    if any(a == "--select" or str(a).startswith("--select=") for a in arguments):
        return "selected"
    return None


def from_arguments(arguments):
    """명령 인수에서 `--select` 값을 찾아 해석한다. 없으면 None."""
    arguments = list(arguments)
    for index, value in enumerate(arguments):
        if value == "--select":
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise ValueError("--select 뒤에 TC 목록을 쉼표로 지정하세요.")
            return resolve(arguments[index + 1].split(","))
        if value.startswith("--select="):
            return resolve(value.split("=", 1)[1].split(","))
    return None

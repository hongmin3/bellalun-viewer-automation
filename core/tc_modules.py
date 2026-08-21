# -*- coding: utf-8 -*-
r"""TC ID → 그 TC 를 구현한 파일 목록.

HTML 리포트가 "이 판정을 만든 코드가 어디에 있는가"를 보여주기 위한 지도다.
리포트만 보고 코드를 찾을 수 있어야 감사가 된다(AGENTS.md 6절).

**자동 추론하지 않고 명시한다.** `tests/workflowNN.py` ↔ `TC_Basic_WorkFlow_NN`
규칙이 대부분 성립하지만, 판정부가 다른 파일에 있는 경우(`tests/dataflow.py`)와
여러 TC 를 한 파일이 담는 경우(`tests/xipl_flows.py`, `tests/install.py`)가 있어
규칙으로 뭉개면 틀린 경로를 보여 준다.

경로는 저장소 루트(`auto/`) 기준 상대 경로다.
"""

TC_MODULES = {
    # --- Install ---
    "TC_Basic_Install_01": ["tests/install.py", "core/sysinfo.py"],
    "TC_Basic_Install_02": ["tests/install.py", "core/sysinfo.py",
                            "core/preflight.py"],
    "TC_Basic_Install_07": ["tests/install.py", "tests/settings.py"],
    "TC_Basic_Install_08": ["tests/install.py", "core/snapshot.py"],
    "TC_Basic_Install_09": ["tests/install.py", "core/snapshot.py"],

    # --- Basic Work Flow ---
    "TC_Basic_WorkFlow_01": ["tests/workflow01.py", "core/mwl.py",
                             "core/flows.py"],
    "TC_Basic_WorkFlow_02": ["tests/workflow02.py", "core/viewer_tools.py",
                             "core/flows.py"],
    "TC_Basic_WorkFlow_03": ["tests/workflow03.py", "core/print_overlay.py"],
    "TC_Basic_WorkFlow_04": ["tests/workflow04.py", "core/send_verify.py",
                             "core/dicomlite.py"],
    "TC_Basic_WorkFlow_05": ["tests/workflow05.py", "core/send_verify.py"],
    "TC_Basic_WorkFlow_06": ["tests/workflow06.py", "core/send_verify.py"],
    "TC_Basic_WorkFlow_07": ["tests/workflow07.py", "core/send_verify.py"],
    "TC_Basic_WorkFlow_08": ["tests/workflow08.py", "core/printscp.py",
                             "core/print_overlay.py"],
    "TC_Basic_WorkFlow_09": ["tests/workflow09.py", "core/export_manager.py"],
    "TC_Basic_WorkFlow_10": ["tests/workflow10.py", "core/mwl.py",
                             "core/dicom_settings.py"],
    "TC_Basic_WorkFlow_11": ["tests/workflow11.py", "tests/dataflow.py"],
    "TC_Basic_WorkFlow_12": ["tests/workflow12.py", "tests/dataflow.py"],
    "TC_Basic_WorkFlow_13": ["tests/workflow13.py", "core/uitext.py"],
    "TC_Basic_WorkFlow_14": ["tests/workflow14.py", "core/setting_transfer.py",
                             "core/setting_values.py", "core/snapshot.py"],
    "TC_Basic_WorkFlow_15": ["tests/workflow15.py", "core/send_verify.py"],
    "TC_Basic_WorkFlow_16": ["tests/workflow16.py"],

    # --- XIPL compatibility ---
    "TC_XIPL_compatibility_01": ["tests/xipl_flows.py", "core/xipl.py"],
    "TC_XIPL_compatibility_02": ["tests/xipl_flows.py",
                                 "core/viewer_processing.py"],
    "TC_XIPL_compatibility_03": ["tests/xipl_flows.py",
                                 "core/viewer_processing.py"],
    "TC_XIPL_compatibility_04": ["tests/xipl_flows.py",
                                 "core/viewer_processing.py"],
    "TC_XIPL_compatibility_05": ["tests/xipl_flows.py",
                                 "core/viewer_processing.py"],
    "TC_XIPL_compatibility_06": ["tests/xipl_flows.py", "core/xipl.py",
                                 "core/viewer_processing.py"],

    # --- 자동화 보조 (개정본 TC 가 아니다) ---
    "AUTOMATION_ENVIRONMENT": ["run.py", "core/display.py", "core/sysinfo.py"],
    "AUTOMATION_ENVIRONMENT_RESET": ["run.py", "core/dbreset.py",
                                     "core/viewer_processing.py"],
    "DICOM_Server_Setup": ["core/dicom_settings.py", "core/net.py",
                           "core/printscp.py"],
    "AUTOMATION_3D_ACQUISITION_3DN": ["tests/system_compat.py",
                                      "core/flows.py"],
    "AUTOMATION_3D_ACQUISITION_3DW": ["tests/system_compat.py",
                                      "core/flows.py"],
}


def modules_for(tc_id):
    """TC ID 의 구현 파일 목록. 모르는 ID 는 빈 목록."""
    return TC_MODULES.get(tc_id, [])


def as_map(tc_ids=None):
    if tc_ids is None:
        return dict(TC_MODULES)
    return {t: TC_MODULES[t] for t in tc_ids if t in TC_MODULES}

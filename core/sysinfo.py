# -*- coding: utf-8 -*-
"""Windows 환경 조회 (설치 프로그램, 서비스, 방화벽, NIC, 파일 버전, 레지스트리)."""

import json
import os
import subprocess


def _ps(script):
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;" + script],
        capture_output=True,
    )
    return proc.stdout.decode("utf-8", "replace").strip()


def _ps_json(script, default=None):
    out = _ps(script)
    if not out:
        return default if default is not None else []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return default if default is not None else []
    return [data] if isinstance(data, dict) else data


def installed_programs():
    """Programs and Features 목록 (DisplayName -> DisplayVersion)."""
    rows = _ps_json(
        r"Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*,"
        r"HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\* "
        r"-ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } | "
        r"Select-Object DisplayName,DisplayVersion | ConvertTo-Json -Compress"
    )
    out = {}
    for r in rows:
        name = (r.get("DisplayName") or "").strip()
        if name and name not in out:
            out[name] = (r.get("DisplayVersion") or "").strip()
    return out


def file_version(path):
    """파일의 FileVersion. 없으면 None."""
    if not os.path.exists(path):
        return None
    v = _ps(f"(Get-Item -LiteralPath '{path}').VersionInfo.FileVersion")
    return v.strip() or None


def service_state(name):
    """서비스 Status/StartType. 없으면 None."""
    # ConvertTo-Json이 열거형을 정수로 직렬화하므로 PowerShell 쪽에서 문자열로 고정한다.
    rows = _ps_json(
        f"Get-Service -Name '{name}' -ErrorAction SilentlyContinue | Select-Object Name,"
        f"@{{n='Status';e={{$_.Status.ToString()}}}},"
        f"@{{n='StartType';e={{$_.StartType.ToString()}}}} | ConvertTo-Json -Compress"
    )
    if not rows:
        return None
    r = rows[0]
    return {"name": r.get("Name"), "status": str(r.get("Status")),
            "start_type": str(r.get("StartType"))}


def firewall_rules(keyword):
    """DisplayName에 keyword가 포함된 활성 방화벽 규칙 이름 목록."""
    rows = _ps_json(
        f"Get-NetFirewallRule -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.DisplayName -like '*{keyword}*' -and $_.Enabled -eq 'True' }} | "
        f"Select-Object DisplayName,Direction,Action | ConvertTo-Json -Compress"
    )
    return [r.get("DisplayName") for r in rows]


def nic_ipv4(alias):
    """지정 어댑터의 IPv4 정보. 어댑터가 없으면 None."""
    rows = _ps_json(
        f"Get-NetAdapter -Name '{alias}' -ErrorAction SilentlyContinue | "
        f"Select-Object Name,Status | ConvertTo-Json -Compress"
    )
    if not rows:
        return None
    ips = _ps_json(
        f"Get-NetIPAddress -InterfaceAlias '{alias}' -AddressFamily IPv4 "
        f"-ErrorAction SilentlyContinue | Select-Object IPAddress,PrefixLength | "
        f"ConvertTo-Json -Compress"
    )
    return {"name": rows[0].get("Name"), "status": str(rows[0].get("Status")),
            "ipv4": [i.get("IPAddress") for i in ips]}


def registry_value(key, name):
    """레지스트리 값. 없으면 None."""
    out = _ps(f"(Get-ItemProperty -Path '{key}' -Name '{name}' -ErrorAction "
              f"SilentlyContinue).'{name}'")
    return out.strip() or None


def process_names():
    return [p for p in _ps("Get-Process | Select-Object -ExpandProperty ProcessName").splitlines()]


def is_elevated():
    out = _ps("([Security.Principal.WindowsPrincipal]"
              "[Security.Principal.WindowsIdentity]::GetCurrent())"
              ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)")
    return out.strip().lower() == "true"


def os_info():
    rows = _ps_json("Get-CimInstance Win32_OperatingSystem | "
                    "Select-Object Caption,Version,BuildNumber,OSArchitecture | "
                    "ConvertTo-Json -Compress")
    return rows[0] if rows else {}

def pc_info():
    """리포트 상단에 실을 **PC 실측 정보**.

    2026-08-21 사용자 요청: OS 정보를 `TC_Basic_Install_02` 의 확인 항목으로 두지
    않고(지원 OS Build 기준이 문서상 확정되지 않아 영구 MANUAL 이 된다) 리포트
    상단의 실행 환경 표에 실측값으로 싣는다.

    한 번의 PowerShell 호출로 모아 온다 — 항목마다 따로 부르면 회귀 시작마다
    수 초가 더 든다.
    """
    rows = _ps_json(
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "$cpu=@(Get-CimInstance Win32_Processor)[0];"
        "$bios=Get-CimInstance Win32_BIOS;"
        "$gpu=@(Get-CimInstance Win32_VideoController | "
        "  Select-Object -ExpandProperty Name) -join '; ';"
        "[pscustomobject]@{"
        " os_caption=$os.Caption; os_version=$os.Version;"
        " os_build=$os.BuildNumber; os_arch=$os.OSArchitecture;"
        " os_install=($os.InstallDate).ToString('yyyy-MM-dd');"
        " os_locale=$os.OSLanguage;"
        " last_boot=($os.LastBootUpTime).ToString('yyyy-MM-dd HH:mm:ss');"
        " host=$cs.Name; domain=$cs.Domain; user=$cs.UserName;"
        " manufacturer=$cs.Manufacturer; model=$cs.Model;"
        " ram_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1);"
        " cpu=$cpu.Name; cpu_cores=$cpu.NumberOfCores;"
        " cpu_threads=$cpu.NumberOfLogicalProcessors;"
        " bios=$bios.SMBIOSBIOSVersion; gpu=$gpu"
        "} | ConvertTo-Json -Compress")
    return rows[0] if rows else {}

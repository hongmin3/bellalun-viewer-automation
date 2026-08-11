# -*- coding: utf-8 -*-
"""네트워크 어댑터 조회 보조."""

from core.sysinfo import _ps_json


def adapters():
    """모든 어댑터의 별칭/상태/IPv4."""
    rows = _ps_json(
        "Get-NetAdapter -ErrorAction SilentlyContinue | Select-Object Name,"
        "@{n='Status';e={$_.Status.ToString()}},InterfaceDescription | "
        "ConvertTo-Json -Compress"
    )
    ips = _ps_json(
        "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Select-Object InterfaceAlias,IPAddress | ConvertTo-Json -Compress"
    )
    by_alias = {}
    for i in ips:
        by_alias.setdefault(i.get("InterfaceAlias"), []).append(i.get("IPAddress"))
    return [{"name": r.get("Name"), "status": r.get("Status"),
             "description": r.get("InterfaceDescription"),
             "ipv4": by_alias.get(r.get("Name"), [])} for r in rows]


def summary():
    return "; ".join(f"{a['name']}({a['status']}"
                     + (f", {', '.join(a['ipv4'])}" if a["ipv4"] else "") + ")"
                     for a in adapters())

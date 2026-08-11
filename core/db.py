# -*- coding: utf-8 -*-
"""BELLALUN SQL Server 조회 브릿지.

ODBC 드라이버/pyodbc 설치 없이 동작하도록 PowerShell + System.Data.SqlClient를
경유한다. 검증 PC에 추가 설치를 요구하지 않는 것이 목적이다.

조회 전용이다. UPDATE/INSERT/DELETE는 의도적으로 제공하지 않는다.
(지침: 파괴적 조작은 명시적 승인과 복구 절차 없이 자동화하지 않는다)
"""

import json
import os
import shutil
import subprocess
import tempfile

_PS_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$cs = "Server=$env:BLN_SERVER;Database=$env:BLN_DB;Integrated Security=True;Connect Timeout=15"
$conn = New-Object System.Data.SqlClient.SqlConnection($cs)
$conn.Open()
try {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $env:BLN_SQL
    if ($env:BLN_PARAMS) {
        $p = $env:BLN_PARAMS | ConvertFrom-Json
        foreach ($k in $p.PSObject.Properties.Name) {
            $v = $p.$k
            if ($null -eq $v) { $v = [System.DBNull]::Value }
            [void]$cmd.Parameters.AddWithValue(('@' + $k), $v)
        }
    }
    $da = New-Object System.Data.SqlClient.SqlDataAdapter($cmd)
    $dt = New-Object System.Data.DataTable
    [void]$da.Fill($dt)
    $rows = @()
    foreach ($r in $dt.Rows) {
        $o = [ordered]@{}
        foreach ($col in $dt.Columns) {
            $val = $r[$col]
            if ($val -is [System.DBNull]) { $val = $null }
            $o[$col.ColumnName] = $val
        }
        $rows += [pscustomobject]$o
    }
    ConvertTo-Json -InputObject @($rows) -Depth 5 -Compress
} finally { $conn.Close() }
"""


_PS_BATCH = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$specs = Get-Content -LiteralPath $env:BLN_SPEC_FILE -Raw -Encoding UTF8 | ConvertFrom-Json
$out = [ordered]@{}
$byDb = @{}
foreach ($s in $specs) {
    if (-not $byDb.ContainsKey($s.db)) { $byDb[$s.db] = @() }
    $byDb[$s.db] += $s
}
foreach ($dbName in $byDb.Keys) {
    $cs = "Server=$env:BLN_SERVER;Database=$dbName;Integrated Security=True;Connect Timeout=15"
    $conn = New-Object System.Data.SqlClient.SqlConnection($cs)
    $conn.Open()
    try {
        foreach ($s in $byDb[$dbName]) {
            try {
                $cmd = $conn.CreateCommand()
                $cmd.CommandText = $s.sql
                $da = New-Object System.Data.SqlClient.SqlDataAdapter($cmd)
                $dt = New-Object System.Data.DataTable
                [void]$da.Fill($dt)
                $rows = @()
                foreach ($r in $dt.Rows) {
                    $o = [ordered]@{}
                    foreach ($col in $dt.Columns) {
                        $val = $r[$col]
                        if ($val -is [System.DBNull]) { $val = $null }
                        $o[$col.ColumnName] = $val
                    }
                    $rows += [pscustomobject]$o
                }
                $out[$s.name] = @($rows)
            } catch {
                $out[$s.name] = @{ _error = $_.Exception.Message }
            }
        }
    } finally { $conn.Close() }
}
ConvertTo-Json -InputObject $out -Depth 6 -Compress |
    Out-File -LiteralPath $env:BLN_OUT_FILE -Encoding UTF8
"""


class DbError(RuntimeError):
    pass


class BellalunDb:
    """DATA / CONFIGURATION / ACCOUNT / PROCEDURE 조회기."""

    def __init__(self, server=r".\BELLALUN"):
        self.server = server

    def query(self, database, sql, params=None):
        """SELECT 결과를 dict 리스트로 반환한다."""
        env = dict(os.environ)
        env["BLN_SERVER"] = self.server
        env["BLN_DB"] = database
        env["BLN_SQL"] = sql
        env["BLN_PARAMS"] = json.dumps(params or {}, ensure_ascii=False)

        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_TEMPLATE],
            capture_output=True, env=env,
        )
        out = proc.stdout.decode("utf-8", "replace").strip()
        err = proc.stderr.decode("utf-8", "replace").strip()
        if proc.returncode != 0:
            raise DbError(f"[{database}] 조회 실패: {err or out}")
        if not out:
            return []
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise DbError(f"[{database}] 응답 파싱 실패: {exc} / raw={out[:500]}")
        if isinstance(data, dict):
            return [data]
        return data

    def query_many(self, specs):
        """여러 쿼리를 PowerShell 1회 호출로 처리한다.

        specs: [{"name":..., "db":..., "sql":...}, ...]
        반환:  {name: rows | {"_error": msg}}

        스냅샷은 수십 개 섹션을 조회하므로 프로세스 기동 비용이 지배적이다.
        DB별 연결 1개를 재사용하여 수십 초를 1~2초로 줄인다.
        """
        if not specs:
            return {}
        tmp = tempfile.mkdtemp(prefix="bln_")
        spec_file = os.path.join(tmp, "spec.json")
        out_file = os.path.join(tmp, "out.json")
        try:
            with open(spec_file, "w", encoding="utf-8") as f:
                json.dump(specs, f, ensure_ascii=False)

            env = dict(os.environ)
            env["BLN_SERVER"] = self.server
            env["BLN_SPEC_FILE"] = spec_file
            env["BLN_OUT_FILE"] = out_file

            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_BATCH],
                capture_output=True, env=env,
            )
            if not os.path.exists(out_file):
                err = proc.stderr.decode("utf-8", "replace").strip()
                raise DbError(f"배치 조회 실패: {err or proc.stdout.decode('utf-8', 'replace')}")
            with open(out_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return {k: (v if isinstance(v, list) else v) for k, v in data.items()}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def one(self, database, sql, params=None):
        """단일 행을 반환한다. 없으면 None."""
        rows = self.query(database, sql, params)
        return rows[0] if rows else None

    def scalar(self, database, sql, params=None, default=None):
        row = self.one(database, sql, params)
        if not row:
            return default
        return next(iter(row.values()))

    def ping(self, database="DATA"):
        """Bellalun 업무 DB 접속 가능 여부.

        master는 항상 열리므로 판정에 쓰면 안 된다. 재설치 직후에는
        DATA/CONFIGURATION 등이 SQL 인스턴스에 attach되기 전이라
        master만 보이는 상태가 실제로 발생한다.
        """
        try:
            self.scalar(database, "SELECT 1 AS ok")
            return True
        except DbError:
            return False

    def databases(self):
        try:
            return [r["name"] for r in
                    self.query("master", "SELECT name FROM sys.databases "
                                         "WHERE database_id > 4")]
        except DbError:
            return []

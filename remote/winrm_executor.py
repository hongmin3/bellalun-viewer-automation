"""Ubuntu/Windows 공용 optional pywinrm adapter. 암호는 로컬 환경 참조로만 읽는다."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile

from remote.bundles import MAX_BYTES, BundleError, check_local, safe_path
from remote.coordinator import RemoteBlocked, RemoteError
from remote.interlock import SharedInterlock
from remote.result_views import derive_views


SESSION_PROBE = r'''
$ErrorActionPreference='Stop'
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class BellalunWts {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
 public struct Level1 {
  public UInt32 SessionId; public Int32 State; public Int32 Flags;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=33)] public string Station;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=21)] public string User;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=18)] public string Domain;
  public Int64 Logon; public Int64 Connect; public Int64 Disconnect; public Int64 LastInput;
  public Int64 Current; public UInt32 Incoming; public UInt32 Outgoing;
  public UInt32 IncomingFrames; public UInt32 OutgoingFrames;
  public UInt32 IncomingCompressed; public UInt32 OutgoingCompressed;
 }
 [StructLayout(LayoutKind.Sequential)] public struct Info { public UInt32 Level; public Level1 Data; }
 [DllImport("kernel32.dll")] public static extern UInt32 WTSGetActiveConsoleSessionId();
 [DllImport("wtsapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 public static extern bool WTSQuerySessionInformation(IntPtr server, UInt32 id, int kind, out IntPtr data, out UInt32 size);
 [DllImport("wtsapi32.dll")] public static extern void WTSFreeMemory(IntPtr data);
 public static Info Read() {
  UInt32 id=WTSGetActiveConsoleSessionId(); IntPtr data; UInt32 size;
  if(id==UInt32.MaxValue || !WTSQuerySessionInformation(IntPtr.Zero,id,25,out data,out size)) throw new Exception("Session query unavailable");
  try { if(size<Marshal.SizeOf(typeof(Info))) throw new Exception("Session structure incomplete");
   return (Info)Marshal.PtrToStructure(data,typeof(Info)); } finally { WTSFreeMemory(data); }
 }
}
'@
$i=[BellalunWts]::Read()
if($i.Level -ne 1){throw 'Unknown session format'}
@{logged_in=($i.Data.State -eq 0 -and [bool]$i.Data.User); unlocked=($i.Data.Flags -eq 1);
 user=($i.Data.Domain+'\'+$i.Data.User); session_id=$i.Data.SessionId} | ConvertTo-Json -Compress
'''


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


class WinRMExecutor:
    def __init__(self, session_factory=None, environ=None, poll_seconds=1):
        self.factory = session_factory
        self.environ = os.environ if environ is None else environ
        self.poll_seconds = poll_seconds
        self.interlock = SharedInterlock(self.environ)
        self.lease_root = None

    def configure_state_root(self, root):
        self.lease_root = check_local(root)
        self.lease_root.mkdir(parents=True, exist_ok=True)

    def acquire_interlock(self, job, pc):
        # 명시적으로 운영 격리를 승인한 로컬 설정만 snapshot-only를 허용한다.
        if pc.get("allow_uncoordinated_vhd_snapshot") is True:
            return None
        if self.lease_root is None:
            raise RemoteBlocked("공용 잠금 복구 기록 저장소가 미설정입니다")
        lease = self.interlock.acquire(job, pc)
        path = self.lease_root / (job["id"] + ".json")
        with path.open("x", encoding="utf-8") as stream:
            json.dump(lease, stream)
            stream.flush()
            os.fsync(stream.fileno())
        return lease

    def release_interlock(self, job, pc, lease):
        if lease is None:
            return
        self.interlock.release(job, pc, lease)
        path = self.lease_root / (job["id"] + ".json")
        data = dict(lease, released=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def verify_completion(self, job, profile, receipt, output, remote_workspace=None):
        run_id = receipt.get("engine_run_id")
        code = receipt.get("exit_code")
        result = {"status": "abnormal", "remote_job_id": job["id"],
                  "engine_run_id": run_id, "exit_code": code,
                  "stopped_verified": receipt.get("job_id") == job["id"] and receipt.get("finished") is True}
        if receipt.get("job_id") != job["id"] or receipt.get("finished") is not True:
            result["status"] = "uncertain"
            return result
        if type(code) is not int:
            return result
        if code in (2, 1223):
            result["status"] = "blocked"
            return result
        if code not in (0, 1) or not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", run_id or ""):
            return result
        try:
            path = check_local(Path(output) / "workspace" / "Runs" / run_id / "run.json")
            record = json.loads(path.read_text(encoding="utf-8-sig"))
            actions = [a for a in profile["argv"] if a in ("run-regression", "run-winupdate")]
            if len(actions) != 1 or (record.get("run_id"), record.get("action"), record.get("status"), record.get("exit_code")) != (run_id, actions[0], "completed", code):
                return result
            reports_dir = Path(output) / "workspace" / "Reports"
            remote_workspace = remote_workspace or receipt.get("workspace")
            if not isinstance(remote_workspace, str):
                return result
            expected_reports = PureWindowsPath(remote_workspace) / "Reports"
            for report_path in reports_dir.glob("Result_*.json"):
                if not any(PureWindowsPath(p) == expected_reports / report_path.name
                           for p in record.get("reports", []) if isinstance(p, str)):
                    continue
                report = json.loads(check_local(report_path).read_text(encoding="utf-8-sig"))
                meta = report.get("meta") or {}
                if (meta.get("run_id") != run_id or meta.get("execution_mode") != "live"
                        or meta.get("chain_completed") is not True or meta.get("presentation_only")
                        or meta.get("report_role") == "presentation"):
                    continue
                ids = {r.get("tc_id") for r in report.get("results", []) if isinstance(r, dict)}
                if actions[0] == "run-winupdate":
                    expected = {f"TC_WindowsUpdate_{i:02}" for i in range(1, 14)}
                else:
                    from core.automation_health import FULL_REGRESSION_MARKERS
                    expected = FULL_REGRESSION_MARKERS
                if expected <= ids:
                    result.update(status="completed", supervisor_run=str(path.relative_to(output)),
                                  primary_report=str(report_path.relative_to(output)))
                    return result
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return result

    def validate(self, pc, profile):
        if pc.get("enabled") is not True:
            raise RemoteError("대상 PC가 승인되지 않았습니다")
        endpoint = urlparse(pc.get("endpoint", ""))
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.path != "/wsman":
            raise RemoteError("TLS WinRM endpoint가 필요합니다")
        if not pc.get("user") or not pc.get("password_env") or not self.environ.get(pc["password_env"]):
            raise RemoteError("로컬 자격증명 환경 참조가 준비되지 않았습니다")
        path = PureWindowsPath(pc.get("work_dir", ""))
        if not path.is_absolute() or not re.fullmatch(r"[A-Za-z]:[\\/][A-Za-z0-9 _\\/.-]+", str(path)):
            raise RemoteError("명시적인 Windows 작업 경로가 필요합니다")
        if ".." in path.parts:
            raise RemoteError("상위 작업 경로를 허용하지 않습니다")
        argv = profile.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v and "\x00" not in v for v in argv):
            raise RemoteError("관리자가 허용한 고정 argv profile이 필요합니다")
        if not isinstance(profile.get("timeout_seconds", 7200), int) or not 1 <= profile.get("timeout_seconds", 7200) <= 86400:
            raise RemoteError("profile 제한 시간이 필요합니다")
        if self.factory is None:
            try:
                import winrm
            except ImportError as exc:
                raise RemoteError("optional remote/requirements.txt의 pywinrm 설치가 필요합니다") from exc

    def _session(self, pc):
        factory = self.factory
        if factory is None:
            import winrm
            factory = winrm.Session
        return factory(pc["endpoint"], auth=(pc["user"], self.environ[pc["password_env"]]),
                       transport="ntlm", server_cert_validation="validate",
                       operation_timeout_sec=30, read_timeout_sec=40)

    def _ps(self, session, script):
        response = session.run_ps(script)
        if response.status_code != 0:
            raise RemoteError("WinRM 명령 실패: 원격 stderr는 비밀 노출 방지를 위해 응답에 포함하지 않습니다")
        output = response.std_out
        return output.decode("utf-8-sig") if isinstance(output, bytes) else str(output)

    def _guard(self, session, pc):
        state = json.loads(self._ps(session, SESSION_PROBE))
        expected = pc.get("interactive_user", pc["user"]).casefold()
        actual = str(state.get("user", "")).casefold()
        user_matches = actual == expected or ("\\" not in expected and actual.rsplit("\\", 1)[-1] == expected)
        if state.get("logged_in") is not True or state.get("unlocked") is not True or not user_matches:
            raise RemoteBlocked("로그인한 승인 사용자 세션이 잠겨 있거나 확인되지 않았습니다")
        return state

    def _vhd_guard(self, pc):
        url = pc.get("vhd_jobs_url")
        if not url:
            raise RemoteBlocked("VHD 작업 충돌 조회 주소가 미설정입니다")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            raise RemoteBlocked("VHD 작업 조회 주소가 유효하지 않습니다")
        with urlopen(url, timeout=10) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RemoteError("VHD 상태 응답 크기 초과")
        data = json.loads(raw)
        jobs = data.get("jobs") if isinstance(data, dict) else data
        if not isinstance(jobs, list):
            raise RemoteError("VHD 작업 상태 형식 미확인")
        target = pc.get("vhd_target")
        if not target:
            raise RemoteError("VHD 충돌 검사 대상이 미설정입니다")
        terminal = {"completed", "failed", "cancelled", "done", "error", "stopped"}
        for job in jobs:
            if not isinstance(job, dict):
                raise RemoteError("VHD 작업 상태 미확인")
            if job.get("ip", job.get("target_ip")) == target and job.get("status") not in terminal:
                raise RemoteBlocked("대상 PC에 VHD 작업이 진행 중입니다")

    def _directory(self, job_id, pc):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", job_id):
            raise RemoteError("잘못된 원격 실행 번호")
        return str(PureWindowsPath(pc["work_dir"]) / job_id)

    def _put(self, session, destination, content):
        # WinRM encoded command 길이 제한 안에서 고정 크기 chunk로 전송한다.
        q = ps_literal(destination)
        self._ps(session, f"$ErrorActionPreference='Stop'; if(Test-Path -LiteralPath {q}){{throw 'Destination exists'}}; [IO.File]::WriteAllBytes({q},[byte[]]@())")
        for offset in range(0, len(content), 1500):
            chunk = base64.b64encode(content[offset:offset + 1500]).decode()
            self._ps(session, f"$s=[IO.File]::Open({q},[IO.FileMode]::Append); try{{$b=[Convert]::FromBase64String('{chunk}');$s.Write($b,0,$b.Length)}}finally{{$s.Dispose()}}")
        expected = hashlib.sha256(content).hexdigest()
        self._ps(session, f"if((Get-FileHash -LiteralPath {q} -Algorithm SHA256).Hash.ToLower() -ne '{expected}'){{throw 'Transfer hash mismatch'}}")

    def _arguments(self, job, pc, profile):
        root = self._directory(job["id"], pc)
        replacements = {"{restore_after}": "--restore-after" if job["restore_after"] else "--no-restore-after",
                        "{run_id}": job["id"], "{workspace}": root + "\\workspace",
                        "{request_file}": root + "\\request.json", "{code}": root + "\\code"}
        result = []
        for argument in profile["argv"]:
            for key, value in replacements.items():
                argument = argument.replace(key, value)
            if "{" in argument or "}" in argument:
                raise RemoteError("허용하지 않은 profile 치환 변수")
            result.append(argument)
        return result

    def task_script(self, job_id, pc, profile):
        root = self._directory(job_id, pc)
        user = pc.get("interactive_user", pc["user"])
        action_argument = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + root + '\\runner.ps1"'
        return f"""$ErrorActionPreference='Stop'
$principal=New-ScheduledTaskPrincipal -UserId {ps_literal(user)} -LogonType Interactive -RunLevel Highest
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {ps_literal(action_argument)} -WorkingDirectory {ps_literal(root + chr(92) + 'code')}
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds {profile.get('timeout_seconds',7200)}) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'BellalunRemote-{job_id}' -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName 'BellalunRemote-{job_id}'
"""

    def _wrapper(self, job, pc, profile):
        root = self._directory(job["id"], pc)
        argv = self._arguments(job, pc, profile)
        arguments = subprocess.list2cmdline(argv[1:])
        return f"""$ErrorActionPreference='Stop'
$env:BELLALUN_REMOTE_JOB_ID={ps_literal(job['id'])}
$root={ps_literal(root)}
try {{
 $child=Start-Process -FilePath {ps_literal(argv[0])} -ArgumentList {ps_literal(arguments)} -WorkingDirectory ($root+'\\code') -PassThru -RedirectStandardOutput ($root+'\\stdout.log') -RedirectStandardError ($root+'\\stderr.log')
 @{{pid=$child.Id; start=$child.StartTime.ToUniversalTime().ToString('o'); path=$child.Path}} | ConvertTo-Json -Compress | Set-Content -LiteralPath ($root+'\\child.json') -Encoding UTF8
 $child.WaitForExit(); $child.Refresh(); $exit=$child.ExitCode
 $records=@(Get-ChildItem -LiteralPath ($root+'\\workspace\\Runs') -Filter 'run.json' -File -Recurse -ErrorAction SilentlyContinue)
 $rid=$null;if($records.Count -eq 1){{$rid=(Get-Content -Raw -LiteralPath $records[0].FullName | ConvertFrom-Json).run_id}}
 @{{job_id={ps_literal(job['id'])};engine_run_id=$rid;workspace=($root+'\\workspace');exit_code=$exit;finished=$true}} | ConvertTo-Json -Compress | Set-Content -LiteralPath ($root+'\\receipt.json') -Encoding UTF8
 exit $exit
}} catch {{
 @{{job_id={ps_literal(job['id'])};finished=$false;error_type=$_.Exception.GetType().Name}} | ConvertTo-Json -Compress | Set-Content -LiteralPath ($root+'\\receipt.json') -Encoding UTF8
 exit 125
}}
""".encode("utf-8-sig")

    def _stop(self, session, job, pc):
        root = self._directory(job["id"], pc)
        script = f"""$ErrorActionPreference='Stop'; $root={ps_literal(root)}
Stop-ScheduledTask -TaskName 'BellalunRemote-{job['id']}' -ErrorAction SilentlyContinue
if(!(Test-Path -LiteralPath ($root+'\\child.json'))){{ @{{stopped=$false}} | ConvertTo-Json -Compress; exit }}
$identity=Get-Content -Raw -LiteralPath ($root+'\\child.json') | ConvertFrom-Json
$p=Get-Process -Id $identity.pid -ErrorAction SilentlyContinue
if($p){{
 if($p.StartTime.ToUniversalTime().ToString('o') -ne $identity.start -or $p.Path -ne $identity.path){{throw 'Process identity mismatch'}}
 & taskkill.exe /PID $identity.pid /T /F | Out-Null
}}
$left=Get-Process -Id $identity.pid -ErrorAction SilentlyContinue
$task=Get-ScheduledTask -TaskName 'BellalunRemote-{job['id']}'
@{{stopped=(!$left -and $task.State -ne 'Running')}} | ConvertTo-Json -Compress
"""
        return json.loads(self._ps(session, script)).get("stopped") is True

    def cancel_existing(self, job, pc):
        stopped = self._stop(self._session(pc), job, pc)
        if stopped and self.lease_root:
            path = self.lease_root / (job["id"] + ".json")
            if path.exists():
                lease = json.loads(path.read_text(encoding="utf-8"))
                if not lease.get("released"):
                    self.release_interlock(job, pc, lease)
        return stopped

    def _collect(self, session, root, output):
        # 수집 범위는 해당 job workspace와 receipt/log뿐이며 임의 경로를 받지 않는다.
        guard = """function Assert-PlainResultPath([string]$path) {
 $current=[IO.Path]::GetFullPath($path)
 while($current){
  if(Test-Path -LiteralPath $current){
   $item=Get-Item -LiteralPath $current -Force
   if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Link result ancestor refused'}
  }
  $parent=[IO.Directory]::GetParent($current)
  if(!$parent){break}; $current=$parent.FullName
 }
}
"""
        script = guard + f"""$ErrorActionPreference='Stop';$root={ps_literal(root)};$files=@()
Assert-PlainResultPath $root
foreach($dir in @('Reports','Evidence','Runs')){{ $p=$root+'\\workspace\\'+$dir;if(Test-Path -LiteralPath $p){{Assert-PlainResultPath $p; Get-ChildItem -LiteralPath $p -Force -Recurse | ForEach-Object {{Assert-PlainResultPath $_.FullName; if(!$_.PSIsContainer){{$files+=$_}}}} }} }}
foreach($name in @('receipt.json','stdout.log','stderr.log')){{if(Test-Path -LiteralPath ($root+'\\'+$name)){{$files+=Get-Item -LiteralPath ($root+'\\'+$name)}}}}
$files | ForEach-Object {{if($_.Attributes -band [IO.FileAttributes]::ReparsePoint){{throw 'Link result refused'}};@{{path=$_.FullName.Substring($root.Length+1).Replace('\\','/');size=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}}}} | ConvertTo-Json -Compress
"""
        records = json.loads(self._ps(session, script))
        if isinstance(records, dict):
            records = [records]
        if not isinstance(records, list) or not records or sum(r["size"] for r in records) > MAX_BYTES:
            raise RemoteError("결과 집합 미확인/크기 초과")
        for record in records:
            relative = record["path"]
            safe_path(relative)
            content = bytearray()
            path = root + "\\" + relative.replace("/", "\\")
            for offset in range(0, record["size"], 32768):
                query = guard + f"Assert-PlainResultPath {ps_literal(path)};$s=[IO.File]::OpenRead({ps_literal(path)});try{{$s.Position={offset};$b=New-Object byte[] 32768;$n=$s.Read($b,0,$b.Length);[Convert]::ToBase64String($b,0,$n)}}finally{{$s.Dispose()}}"
                content.extend(base64.b64decode(self._ps(session, query).strip(), validate=True))
            if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise RemoteError("결과 전송 해시 불일치")
            destination = check_local(output / relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    def execute(self, job, pc, profile, package, output, cancel, log):
        marker = {"task_requested": False}
        lease = None
        try:
            self.validate(pc, profile)
            lease = self.acquire_interlock(job, pc)
            outcome = self._execute(job, pc, profile, package, output, cancel, log, marker)
            if not marker["task_requested"] or outcome.get("stopped_verified") or outcome.get("status") == "completed":
                self.release_interlock(job, pc, lease)
            return outcome
        except Exception as exc:
            if not marker["task_requested"]:
                self.release_interlock(job, pc, lease)
                raise RemoteBlocked("사용자 세션 작업 시작 전 준비 실패") from exc
            raise

    def _execute(self, job, pc, profile, package, output, cancel, log, marker):
        self.validate(pc, profile)
        session = self._session(pc)
        self._guard(session, pc)  # 확인 실패 시 원격 파일/작업 생성 전 거부
        self._vhd_guard(pc)
        if cancel.is_set():
            return {"status": "cancelled", "stopped_verified": True}
        root = self._directory(job["id"], pc)
        self._ps(session, f"$ErrorActionPreference='Stop';if(Test-Path -LiteralPath {ps_literal(root)}){{throw 'Job directory exists'}};New-Item -ItemType Directory -Path {ps_literal(root)} | Out-Null;New-Item -ItemType Directory -Path {ps_literal(root + chr(92) + 'workspace')} | Out-Null")
        self._put(session, root + "\\package.zip", package)
        # ZIP 경로 집합은 업로드 때 검증됐고 원격 전송은 ZIP 전체 SHA-256으로 대조했다.
        self._ps(session, f"$ErrorActionPreference='Stop';Expand-Archive -LiteralPath {ps_literal(root + chr(92) + 'package.zip')} -DestinationPath {ps_literal(root + chr(92) + 'expanded')};Move-Item -LiteralPath {ps_literal(root + chr(92) + 'expanded' + chr(92) + 'payload')} -Destination {ps_literal(root + chr(92) + 'code')}")
        self._put(session, root + "\\request.json", json.dumps(job).encode())
        self._put(session, root + "\\runner.ps1", self._wrapper(job, pc, profile))
        self._guard(session, pc)
        self._vhd_guard(pc)
        marker["task_requested"] = True  # Start 요청 뒤 통신 단절은 미실행으로 추정하지 않는다.
        self._ps(session, self.task_script(job["id"], pc, profile))
        log("사용자 세션 예약 작업 시작; 코드 묶음 " + job["bundle_id"])
        deadline = time.monotonic() + profile.get("timeout_seconds", 7200)
        while True:
            if cancel.is_set() or time.monotonic() >= deadline:
                stopped = self._stop(session, job, pc)
                return {"status": "cancelled" if stopped else "uncertain", "stopped_verified": stopped}
            query = f"if(Test-Path -LiteralPath {ps_literal(root + chr(92) + 'receipt.json')}){{Get-Content -Raw -LiteralPath {ps_literal(root + chr(92) + 'receipt.json')}}}else{{'null'}}"
            receipt = json.loads(self._ps(session, query))
            if receipt:
                self._collect(session, root, output)
                outcome = self.verify_completion(job, profile, receipt, output, root + "\\workspace")
                derive_views(output, root + "\\workspace")
                self._ps(session, f"Unregister-ScheduledTask -TaskName 'BellalunRemote-{job['id']}' -Confirm:$false")
                return outcome
            cancel.wait(self.poll_seconds)

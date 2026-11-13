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

SMALL_TRANSFER_LIMIT = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 6 * 60 * 60
DEFAULT_STOP_GRACE_SECONDS = 30 * 60
BUNDLE_PATH_GUARD = r'''function Assert-PlainBundlePath([string]$path) {
 $p=[IO.Path]::GetFullPath($path)
 while($p){
  if(Test-Path -LiteralPath $p){
   if((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Bundle reparse path refused'}
  }
  $parent=[IO.Directory]::GetParent($p);if(!$parent){break};$p=$parent.FullName
 }
}
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
        timeout = profile.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise RemoteError("profile 제한 시간이 필요합니다")
        if any(action in argv for action in ("run-regression", "run-winupdate")):
            worst = profile.get("worst_case_seconds")
            if type(worst) is not int or worst <= 0 or worst >= timeout:
                raise RemoteBlocked("제품 실행 profile의 최악 예상 시간보다 timeout을 크게 설정하세요")
        grace = profile.get("stop_grace_seconds", DEFAULT_STOP_GRACE_SECONDS)
        if type(grace) is not int or not 1 <= grace <= 7200:
            raise RemoteBlocked("정리·복원 대기 시간은 1~7200초여야 합니다")
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
        if len(content) > SMALL_TRANSFER_LIMIT:
            raise RemoteBlocked("WinRM chunk 전송은 64 KiB 이하 제어 파일에만 허용합니다")
        # WinRM encoded command 길이 제한 안에서 고정 크기 chunk로 전송한다.
        q = ps_literal(destination)
        self._ps(session, f"$ErrorActionPreference='Stop'; if(Test-Path -LiteralPath {q}){{throw 'Destination exists'}}; [IO.File]::WriteAllBytes({q},[byte[]]@())")
        for offset in range(0, len(content), 1500):
            chunk = base64.b64encode(content[offset:offset + 1500]).decode()
            self._ps(session, f"$s=[IO.File]::Open({q},[IO.FileMode]::Append); try{{$b=[Convert]::FromBase64String('{chunk}');$s.Write($b,0,$b.Length)}}finally{{$s.Dispose()}}")
        expected = hashlib.sha256(content).hexdigest()
        self._ps(session, f"if((Get-FileHash -LiteralPath {q} -Algorithm SHA256).Hash.ToLower() -ne '{expected}'){{throw 'Transfer hash mismatch'}}")

    def ensure_package(self, session, job, pc, package):
        self._directory(job["id"], pc)
        identity = job.get("bundle_id", "")
        if not re.fullmatch(r"[0-9a-f]{64}", identity) or len(package) > MAX_BYTES:
            raise RemoteBlocked("묶음 ID/크기 제한 불일치")
        digest = hashlib.sha256(package).hexdigest()
        cache = str(PureWindowsPath(pc["work_dir"]) / ".bundle-cache" / identity)
        destination = str(PureWindowsPath(cache) / (digest + ".zip"))
        state = json.loads(self._ps(session, BUNDLE_PATH_GUARD + f"""
# BELLALUN_BUNDLE_CACHE_PROBE
$ErrorActionPreference='Stop';$cache={ps_literal(cache)};$zip={ps_literal(destination)}
Assert-PlainBundlePath $cache;Assert-PlainBundlePath $zip
if(Test-Path -LiteralPath $zip){{
 if((Get-Item -LiteralPath $zip).PSIsContainer -or (Get-Item -LiteralPath $zip).Length -ne {len(package)} -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() -ne '{digest}'){{throw 'Cached ZIP hash mismatch'}}
 @{{hit=$true}} | ConvertTo-Json -Compress
}}else{{@{{hit=$false}} | ConvertTo-Json -Compress}}
"""))
        if not isinstance(state, dict) or type(state.get("hit")) is not bool:
            raise RemoteBlocked("묶음 캐시 조회 결과 미확인")
        if state["hit"]:
            return destination
        base = pc.get("bundle_download_base")
        token_env = pc.get("bundle_token_env")
        if not base or not token_env:
            if len(package) > SMALL_TRANSFER_LIMIT:
                raise RemoteBlocked("대용량 묶음에는 PC 로컬 token 참조와 HTTPS 다운로드 설정이 필요합니다")
            self._ps(session, BUNDLE_PATH_GUARD + f"$ErrorActionPreference='Stop';Assert-PlainBundlePath {ps_literal(cache)};New-Item -ItemType Directory -Force -Path {ps_literal(cache)} | Out-Null;Assert-PlainBundlePath {ps_literal(cache)}")
            partial = str(PureWindowsPath(cache) / (digest + "." + job["id"] + ".part"))
            self._put(session, partial, package)
            self._ps(session, BUNDLE_PATH_GUARD + f"$ErrorActionPreference='Stop';Assert-PlainBundlePath {ps_literal(partial)};Assert-PlainBundlePath {ps_literal(destination)};[IO.File]::Move({ps_literal(partial)},{ps_literal(destination)})")
            return destination
        parsed = urlparse(base)
        timeout = pc.get("bundle_download_timeout_seconds", 1800)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", token_env)
                or type(timeout) is not int or not 1 <= timeout <= 7200):
            raise RemoteBlocked("유효한 HTTPS 묶음 다운로드와 token 환경 참조가 필요합니다")
        url = base.rstrip("/") + "/bundles/" + identity + "/download"
        partial = str(PureWindowsPath(cache) / (digest + "." + job["id"] + ".part"))
        self._ps(session, BUNDLE_PATH_GUARD + f"""
# BELLALUN_BUNDLE_HTTPS_DOWNLOAD
$ErrorActionPreference='Stop';$cache={ps_literal(cache)};$zip={ps_literal(destination)};$tmp={ps_literal(partial)}
Assert-PlainBundlePath $cache;Assert-PlainBundlePath $zip;Assert-PlainBundlePath $tmp
if((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath $tmp)){{throw 'Download destination exists'}}
New-Item -ItemType Directory -Force -Path $cache | Out-Null;Assert-PlainBundlePath $cache
$token=[Environment]::GetEnvironmentVariable({ps_literal(token_env)})
if(!$token){{$token=[Environment]::GetEnvironmentVariable({ps_literal(token_env)},'User')}}
if(!$token){{$token=[Environment]::GetEnvironmentVariable({ps_literal(token_env)},'Machine')}}
if(!$token){{throw 'Local download token missing'}}
try{{Invoke-WebRequest -Uri {ps_literal(url)} -Headers @{{Authorization=('Bearer '+$token)}} -OutFile $tmp -UseBasicParsing -MaximumRedirection 0 -TimeoutSec {timeout} | Out-Null}}finally{{$token=$null}}
Assert-PlainBundlePath $tmp
if((Get-Item -LiteralPath $tmp).Length -ne {len(package)} -or (Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToLower() -ne '{digest}'){{throw 'Downloaded ZIP hash mismatch'}}
Assert-PlainBundlePath $zip;[IO.File]::Move($tmp,$zip);Assert-PlainBundlePath $zip
""")
        return destination

    def _arguments(self, job, pc, profile):
        root = self._directory(job["id"], pc)
        replacements = {"{restore_after}": "--restore-after" if job["restore_after"] else "--no-restore-after",
                        "{run_id}": job["id"], "{workspace}": root + "\\workspace",
                        "{request_file}": root + "\\request.json", "{code}": root + "\\code",
                        "{stop_file}": root + "\\stop.request"}
        result = []
        for argument in profile["argv"]:
            for key, value in replacements.items():
                argument = argument.replace(key, value)
            if "{" in argument or "}" in argument:
                raise RemoteError("허용하지 않은 profile 치환 변수")
            result.append(argument)
        if any(action in result for action in ("run-regression", "run-winupdate")):
            action_index = next(i for i, value in enumerate(result)
                                if value in ("run-regression", "run-winupdate"))
            if "--stop-file" not in result:
                result[action_index:action_index] = ["--stop-file", root + "\\stop.request"]
            elif (result.index("--stop-file") + 1 >= len(result)
                  or result[result.index("--stop-file") + 1] != root + "\\stop.request"
                  or result.index("--stop-file") >= action_index):
                raise RemoteBlocked("stop-file은 이번 job 내부 경로만 허용합니다")
        return result

    def task_script(self, job_id, pc, profile):
        root = self._directory(job_id, pc)
        user = pc.get("interactive_user", pc["user"])
        action_argument = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + root + '\\runner.ps1"'
        return f"""$ErrorActionPreference='Stop'
$principal=New-ScheduledTaskPrincipal -UserId {ps_literal(user)} -LogonType Interactive -RunLevel Highest
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {ps_literal(action_argument)} -WorkingDirectory {ps_literal(root + chr(92) + 'code')}
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds {profile.get('timeout_seconds',DEFAULT_TIMEOUT_SECONDS) + profile.get('stop_grace_seconds',DEFAULT_STOP_GRACE_SECONDS) + 60}) -MultipleInstances IgnoreNew
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
$task=Get-ScheduledTask -TaskName 'BellalunRemote-{job['id']}' -ErrorAction SilentlyContinue
@{{stopped=(!$left -and $task.State -ne 'Running')}} | ConvertTo-Json -Compress
"""
        return json.loads(self._ps(session, script)).get("stopped") is True

    def cancel_existing(self, job, pc):
        session = self._session(pc)
        root = self._directory(job["id"], pc)
        self._request_stop(session, root)
        grace = pc.get("recovery_stop_grace_seconds", DEFAULT_STOP_GRACE_SECONDS)
        if type(grace) is not int or not 1 <= grace <= 7200:
            raise RemoteError("복구 중단 대기 시간 설정 오류")
        deadline = time.monotonic() + grace
        stopped = False
        while time.monotonic() < deadline:
            receipt = self._poll(session, root).get("receipt")
            if receipt and receipt.get("job_id") == job["id"] and receipt.get("finished") is True:
                run_id = receipt.get("engine_run_id")
                if not isinstance(run_id, str) or not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", run_id):
                    break
                path = str(PureWindowsPath(root) / "workspace" / "Runs" / run_id / "run.json")
                record = json.loads(self._ps(session, BUNDLE_PATH_GUARD + f"Assert-PlainBundlePath {ps_literal(path)};Get-Content -Raw -LiteralPath {ps_literal(path)}"))
                valid = (record.get("run_id") == run_id and record.get("exit_code") == receipt.get("exit_code")
                         and ((record.get("status") == "stopped" and record.get("exit_code") == 130)
                              or (record.get("status") == "completed" and record.get("exit_code") in (0, 1))))
                if valid:
                    restoration_path = str(PureWindowsPath(root) / "workspace" / "preservation" / run_id / "restoration.json")
                    restoration = json.loads(self._ps(session, BUNDLE_PATH_GUARD + f"Assert-PlainBundlePath {ps_literal(restoration_path)};if(Test-Path -LiteralPath {ps_literal(restoration_path)}){{Get-Content -Raw -LiteralPath {ps_literal(restoration_path)}}}else{{'null'}}"))
                    expected = "verified" if job.get("restore_after") is True else "preserved"
                    if isinstance(restoration, dict) and restoration.get("run_id") == run_id and restoration.get("status") == expected:
                        stopped = self._stop(session, job, pc)
                break
            time.sleep(self.poll_seconds)
        if not stopped:
            self._stop(session, job, pc)  # 최후 수단. 정리 완료가 미확인이므로 여전히 False.
            return False
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
foreach($r in @($files | Where-Object {{$_.Name -eq 'run.json' -and $_.Directory.Parent.Name -eq 'Runs'}})){{
 $rid=$r.Directory.Name
 if($rid -match '^[0-9]{{8}}-[0-9]{{6}}-[a-f0-9]{{8}}$'){{
  $p=$root+'\\workspace\\preservation\\'+$rid+'\\restoration.json';Assert-PlainResultPath $p
  if(Test-Path -LiteralPath $p){{$files+=Get-Item -LiteralPath $p}}
 }}
}}
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

    def _poll(self, session, root):
        script = BUNDLE_PATH_GUARD + f"""
# BELLALUN_EXECUTION_POLL
$ErrorActionPreference='Stop';$root={ps_literal(root)};$receipt=$null;$progress=$null;$tail=@()
Assert-PlainBundlePath $root
foreach($kind in @('receipt','progress')){{
 $p=if($kind -eq 'receipt'){{$root+'\\receipt.json'}}else{{$root+'\\workspace\\work\\qa_progress.json'}}
 Assert-PlainBundlePath $p
 if(Test-Path -LiteralPath $p){{
  if((Get-Item -LiteralPath $p).Length -gt 16384){{throw 'Polling JSON too large'}}
  $v=Get-Content -Raw -LiteralPath $p | ConvertFrom-Json
  if($kind -eq 'receipt'){{$receipt=$v}}else{{$progress=$v}}
 }}
}}
$log=$root+'\\stdout.log';Assert-PlainBundlePath $log
if(Test-Path -LiteralPath $log){{$tail=@(Get-Content -LiteralPath $log -Tail 5 | ForEach-Object {{$line=[string]$_;if($line.Length -gt 500){{$line=$line.Substring(0,500)}};$line}})}}
@{{receipt=$receipt;progress=$progress;tail=$tail}} | ConvertTo-Json -Depth 6 -Compress
"""
        raw = self._ps(session, script)
        if len(raw.encode("utf-8")) > 65536:
            raise RemoteError("진행 조회 응답 크기 초과")
        state = json.loads(raw)
        if (not isinstance(state, dict) or not isinstance(state.get("tail"), list)
                or len(state["tail"]) > 5 or not all(isinstance(line, str) and len(line) <= 500 for line in state["tail"])
                or (state.get("receipt") is not None and not isinstance(state["receipt"], dict))
                or (state.get("progress") is not None and not isinstance(state["progress"], dict))):
            raise RemoteError("진행 조회 형식 미확인")
        return state

    def _emit_progress(self, state, seen, log, pc):
        progress = state.get("progress") or {}
        run_id, tc = progress.get("run_id"), progress.get("current_tc")
        index, total = progress.get("index"), progress.get("total")
        if (isinstance(run_id, str) and re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", run_id)
                and isinstance(tc, str) and type(index) is int and type(total) is int
                and 0 <= index <= total <= 20000):
            key = (run_id, tc[:120], index, total)
            if seen.get("progress") != key:
                log(f"진행 {run_id} · {tc[:120]} · {index}/{total}")
                seen["progress"] = key
        tail = state.get("tail") or []
        previous = seen.get("tail", [])
        overlap = 0
        for size in range(min(len(previous), len(tail)), 0, -1):
            if previous[-size:] == tail[:size]:
                overlap = size
                break
        for line in tail[overlap:]:
            for name in (pc.get("password_env"), pc.get("bundle_token_env")):
                secret = self.environ.get(name, "") if name else ""
                if secret:
                    line = line.replace(secret, "[비밀값 제거]")
            if re.search(r"(?i)(password|passwd|access[_-]?token|api[_-]?key)\s*[:=]", line):
                line = "[인증값이 포함될 수 있는 원격 로그 생략]"
            log(line.replace("\r", " ").replace("\n", " ")[:500])
        seen["tail"] = tail

    def _request_stop(self, session, root):
        self._ps(session, BUNDLE_PATH_GUARD + f"$ErrorActionPreference='Stop';$p={ps_literal(root + chr(92) + 'stop.request')};Assert-PlainBundlePath $p;[IO.File]::WriteAllText($p,'cooperative-stop')")

    def _finish_receipt(self, session, job, pc, profile, output, receipt, *, cancelling=False):
        root = self._directory(job["id"], pc)
        self._collect(session, root, output)
        outcome = self.verify_completion(job, profile, receipt, output, root + "\\workspace")
        run_id = receipt.get("engine_run_id")
        cleanup_verified = False
        if isinstance(run_id, str) and re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", run_id):
            restoration_path = check_local(output / "workspace" / "preservation" / run_id / "restoration.json")
            if restoration_path.is_file():
                restoration = json.loads(restoration_path.read_text(encoding="utf-8-sig"))
                expected = "verified" if job.get("restore_after") is True else "preserved"
                cleanup_verified = restoration.get("run_id") == run_id and restoration.get("status") == expected
        outcome["cleanup_verified"] = cleanup_verified
        if (cancelling and receipt.get("job_id") == job["id"] and receipt.get("finished") is True
                and receipt.get("exit_code") == 130):
            if isinstance(run_id, str) and re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", run_id):
                path = check_local(output / "workspace" / "Runs" / run_id / "run.json")
                record = json.loads(path.read_text(encoding="utf-8-sig"))
                if (record.get("run_id") == run_id and record.get("status") == "stopped"
                        and record.get("exit_code") == 130 and cleanup_verified):
                    outcome.update(status="cancelled", stopped_verified=True, cleanup_verified=True)
        if not cleanup_verified:
            outcome.update(engine_status=outcome["status"], status="uncertain",
                           process_stopped_verified=outcome.get("stopped_verified", False),
                           stopped_verified=False, cleanup_verified=False)
        derive_views(output, root + "\\workspace")
        self._ps(session, f"Unregister-ScheduledTask -TaskName 'BellalunRemote-{job['id']}' -Confirm:$false")
        return outcome

    def _cancel_running(self, session, job, pc, profile, output, log, seen):
        root = self._directory(job["id"], pc)
        log("앱에 중단을 요청하고 보존·복원 정리 완료를 기다립니다.")
        self._request_stop(session, root)
        deadline = time.monotonic() + profile.get("stop_grace_seconds", DEFAULT_STOP_GRACE_SECONDS)
        while time.monotonic() < deadline:
            state = self._poll(session, root)
            self._emit_progress(state, seen, log, pc)
            receipt = state.get("receipt")
            if receipt and receipt.get("job_id") == job["id"] and receipt.get("finished") is True:
                return self._finish_receipt(session, job, pc, profile, output, receipt, cancelling=True)
            time.sleep(self.poll_seconds)
        log("정리 대기 시간 초과: 식별된 자식만 최후 수단으로 중지하며 복구 확인 전 잠금을 유지합니다.")
        stopped = self._stop(session, job, pc)
        return {"status": "uncertain", "stopped_verified": False, "process_stopped_verified": stopped,
                "cleanup_verified": False, "forced_stop": True}

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
            # 시작 뒤의 수집/lease 오류도 예외 클래스가 준비 차단과 같을 수 있다.
            # coordinator가 이를 미시작으로 처리해 PC 잠금을 풀지 못하게 한다.
            raise RemoteError("작업 시작 뒤 정리·복원 확인 실패; PC 잠금을 유지합니다") from exc

    def _execute(self, job, pc, profile, package, output, cancel, log, marker):
        self.validate(pc, profile)
        session = self._session(pc)
        self._guard(session, pc)  # 확인 실패 시 원격 파일/작업 생성 전 거부
        self._vhd_guard(pc)
        if cancel.is_set():
            return {"status": "cancelled", "stopped_verified": True}
        root = self._directory(job["id"], pc)
        self._ps(session, f"$ErrorActionPreference='Stop';if(Test-Path -LiteralPath {ps_literal(root)}){{throw 'Job directory exists'}};New-Item -ItemType Directory -Path {ps_literal(root)} | Out-Null;New-Item -ItemType Directory -Path {ps_literal(root + chr(92) + 'workspace')} | Out-Null")
        package_path = self.ensure_package(session, job, pc, package)
        # ZIP 경로 집합은 업로드 때 검증됐고 원격 전송은 ZIP 전체 SHA-256으로 대조했다.
        self._ps(session, BUNDLE_PATH_GUARD + f"$ErrorActionPreference='Stop';Assert-PlainBundlePath {ps_literal(package_path)};if((Get-FileHash -LiteralPath {ps_literal(package_path)} -Algorithm SHA256).Hash.ToLower() -ne '{hashlib.sha256(package).hexdigest()}'){{throw 'Cached ZIP changed'}};Expand-Archive -LiteralPath {ps_literal(package_path)} -DestinationPath {ps_literal(root + chr(92) + 'expanded')};Move-Item -LiteralPath {ps_literal(root + chr(92) + 'expanded' + chr(92) + 'payload')} -Destination {ps_literal(root + chr(92) + 'code')}")
        self._put(session, root + "\\request.json", json.dumps(job).encode())
        self._put(session, root + "\\runner.ps1", self._wrapper(job, pc, profile))
        self._guard(session, pc)
        self._vhd_guard(pc)
        marker["task_requested"] = True  # Start 요청 뒤 통신 단절은 미실행으로 추정하지 않는다.
        self._ps(session, self.task_script(job["id"], pc, profile))
        log("사용자 세션 예약 작업 시작; 코드 묶음 " + job["bundle_id"])
        deadline = time.monotonic() + profile.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        seen = {}
        while True:
            if cancel.is_set() or time.monotonic() >= deadline:
                return self._cancel_running(session, job, pc, profile, output, log, seen)
            state = self._poll(session, root)
            self._emit_progress(state, seen, log, pc)
            receipt = state.get("receipt")
            if receipt:
                return self._finish_receipt(session, job, pc, profile, output, receipt)
            cancel.wait(self.poll_seconds)

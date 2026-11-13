# Bellalun 원격 실행 기반

이 모듈은 코드 묶음을 서버에 보내고 등록한 PC의 허용 profile을 사용자 세션 예약 작업으로 실행한다. 기존 VHD 서버와 별도 프로세스이며 설치·배포·서비스 변경을 수행하지 않는다. 실제 Windows PC·계정·TLS 인증서·런타임이 확정되지 않으면 실행을 차단한다.

## 로컬에서 검증한 범위

`python -m pytest tests/test_remote_execution.py -q`는 실제 localhost HTTP 전송, 인증 거부, 묶음 해시 검증, PC 중복 실행 거부, 취소, SQLite 재시작 상태, CLI 업로드→제출→결과 회수 subprocess, supervisor/리포트 완료 검증을 시험한다. WinRM은 가짜 client로 명령·자격증명 경계와 전송/결과 검증을 시험한다. 임시 브라우저에서 localhost 대시보드 로그인·제출·취소·결과 ZIP 다운로드·로그아웃을 확인했다. 실제 제품 실행, 실제 Windows 예약 작업, 서버 배포 수용은 수행하지 않았다.

서버는 Python 표준 라이브러리로 동작한다. 실제 WinRM adapter에만 `python -m pip install -r remote/requirements.txt`가 필요하다. `pywinrm`이 없으면 모의 실행으로 바꾸지 않고 차단한다.

## 서버 로컬 설정

설정은 저장소 밖의 관리자가 접근 권한을 제한한 JSON 파일에 둔다. endpoint·계정·대상·암호를 공개 저장소에 넣지 않는다. 아래 값은 형식을 설명하는 자리표시자다.

```json
{
  "state_dir": "/var/lib/bellalun-remote",
  "port": 9195,
  "pcs": {
    "qa-pc": {
      "enabled": false,
      "endpoint": "https://pc.example.invalid:5986/wsman",
      "user": "ACCOUNT_FROM_POLICY",
      "interactive_user": "ACCOUNT_FROM_POLICY",
      "password_env": "BELLALUN_PC_PASSWORD",
      "work_dir": "C:\\BellalunRemote",
      "shared_interlock": {
        "url": "https://lock.example.invalid/leases",
        "target": "TARGET_FROM_POLICY",
        "token_env": "BELLALUN_INTERLOCK_TOKEN"
      },
      "vhd_jobs_url": "http://127.0.0.1:5050/api/jobs",
      "vhd_target": "TARGET_FROM_POLICY"
    }
  },
  "profiles": {
    "regression": {
      "argv": [
        "{code}\\BellalunAuto.exe",
        "--workspace", "{workspace}",
        "--config", "C:\\BellalunLocal\\config.json",
        "run-regression", "{restore_after}"
      ],
      "timeout_seconds": 14400
    }
  }
}
```

서버의 `/`는 비밀이나 실행 정보를 포함하지 않는 로그인 shell이다. 접근 토큰을 입력하면 인증 API로 PC·고정 profile·코드 묶음 목록과 실행 상태를 읽는다. 토큰은 `sessionStorage`에만 저장하고 입력란을 비운다. 실행 제출에는 복원 여부 선택이 필요하며 실행별 로그·취소·결과 ZIP 다운로드를 제공한다. 상태는 3초마다 갱신한다. 모든 API는 bearer 인증을 요구하고 초기 HTML/JS에 토큰을 넣지 않는다.

`BELLALUN_REMOTE_TOKEN`과 PC의 `password_env`가 가리키는 비밀 값은 서버 프로세스의 로컬 환경에서 제공한다. 암호를 argv, profile, 로그, 요청 JSON에 넣지 않는다. WinRM은 TLS 인증서 검증을 강제하며 인증서 검증 생략 옵션을 제공하지 않는다. 서버 HTTP는 loopback에만 bind한다. 외부 접근은 별도로 승인·검증한 TLS 프록시/터널을 사용한다.

```text
python tools/remote_execution.py serve --config <서버-로컬-설정.json>
python tools/remote_execution.py bundle <원본> <새-묶음.zip> run.py core/__init__.py
python tools/remote_execution.py upload <새-묶음.zip> <bundle_id>
python tools/remote_execution.py submit qa-pc regression <bundle_id> --restore-after
python tools/remote_execution.py status <job_id>
python tools/remote_execution.py logs <job_id>
python tools/remote_execution.py cancel <job_id>
python tools/remote_execution.py collect <job_id> <존재하지-않는-결과-폴더>
```

묶음은 명시한 파일만 포함한다. 운영 config, DICOM, 백업, Evidence/Reports, work, `.git`, 비밀 키는 코드 묶음에서 거부한다. 실제 배포용 묶음에는 실행 파일 또는 승인한 Python 런타임·의존성·OCR 자산 전체가 필요하다. 예제의 두 Python 파일은 전송 동작을 설명하며 제품 실행에 충분한 배포 묶음이 아니다. 최대 파일 수는 20,000개, 압축 전/후 크기 제한은 512 MiB다.

## 실행과 복구 계약

- 요청은 `pc_id`, `profile_id`, 고정 `bundle_id`, 복원 bool만 받는다. 임의 command/argv는 받지 않는다. profile은 관리자가 허용한 고정 argv이며 `{code}`, `{workspace}`, `{request_file}`, `{run_id}`, `{restore_after}`만 치환한다.
- `{restore_after}`는 `--restore-after` 또는 `--no-restore-after` 한 값이다. `{run_id}`는 원격 job ID다. 엔진의 `--run-id`에 넘기지 않는다. `BELLALUN_REMOTE_JOB_ID`와 회수한 실행 receipt로 엔진 실행 기록을 연결한다.
- 사전 WTSINFOEX 조회로 승인 사용자가 로그인했고 console 세션이 unlocked인지 확인한다. 조회 불가·잠금·사용자 불일치는 파일/예약 작업 생성 전에 거부한다. 전송 뒤 task 시작 직전 다시 확인한다.
- 작업은 `Interactive` logon과 `Highest` 권한의 예약 작업이다. Windows 10/11의 console 세션을 대상으로 한다. 자동 로그온·잠금 해제·방화벽 변경·PC 재부팅은 하지 않는다.
- PC 중복 잠금은 SQLite unique index로 유지한다. 서버 재시작 시 진행 중 상태는 `uncertain`이 되어 잠금이 남는다. `cancel`은 원격 task와 PID·시작 시각·실행 파일 신원을 확인하고 종료 확인 뒤 해제한다. 종료 확인 불가는 `uncertain`이다. 임의 강제 해제 API는 없다.
- 코드 ZIP은 업로드 때 파일 집합·SHA-256을 검증하고 실행 직전 다시 검증한다. WinRM chunk 전송은 ZIP SHA-256을 확인한 뒤 확장한다. 결과는 해당 job의 Reports/Evidence·receipt·stdout/stderr에 한정하고 파일별 크기·SHA-256으로 검증한다.
- 결과 수집에는 해당 workspace의 `Runs/<engine_run_id>/run.json`도 포함한다. receipt의 원격 job ID·엔진 run ID·종료 코드, supervisor의 completed 상태, 동일 실행 번호의 live·chain_completed 리포트와 전체 회귀/WU 표식을 모두 확인해야 `completed`다. 정상 완주한 제품 FAIL(exit 1)도 completed이며 exit 2는 blocked, exit 3·리포트 누락·불완전 완주는 abnormal이다. 프로세스 종료 자체를 확인하지 못하면 uncertain이다.
- 회수 원본 리포트와 해시는 그대로 유지한다. `view/Reports`와 `view/Evidence`는 수집된 파일만 상대경로로 연결한 보기 사본이며, 임의 외부 참조는 수집하지 않는다. `view-derivations.json`은 원본과 파생 파일의 SHA-256을 기록한다. CLI collect는 다운로드 후 전체 manifest와 파일 해시를 대조하고, 웹 다운로드는 ZIP 전송 해시를 확인한다.
- PC 파일·서버 묶음·결과는 자동 삭제하지 않는다. 운영 전 결과 용량·보관 기간 정책을 확정해야 한다.

## 실물 수용 전 남은 조건

실제 PC의 WinRM TLS, 로그인한 전용 실행 계정과 최고 권한, 전체 runtime/code 묶음, 로컬 제품 config, 잠금/취소/결과 실물 시험과 기존 승인 절차가 필요하다. 로그 API는 서버 실행 경계 이벤트를 제공하며 제품 stdout/stderr는 종료 후 결과로 수집한다.

공용 잠금이 미설정이면 기본적으로 시작을 차단한다. `shared_interlock.url`은 VHD와 QA 모두가 반드시 통과하는 외부 lock authority여야 한다. 이 모듈은 그 서비스를 설치하거나 기존 VHD 서비스를 수정하지 않는다. 단순 VHD idle 조회는 공용 잠금 성공으로 취급하지 않는다.

lock authority 계약은 POST `<url>/acquire`에 `{target, owner:job_id, domain:"vhd-and-qa", durable:true}`를 보내며 `{lease_id,target,owner,domain,exclusive:true,durable:true}`를 받아야 한다. 자동 만료하는 lease는 거부한다. 서비스는 같은 owner의 acquire와 release를 멱등 처리하고, 서버가 재시작하거나 통신이 끊겨도 원격 프로세스 종료 확인 전 잠금을 유지해야 한다. POST `<url>/release`는 `{lease_id,target,owner}`를 검증하고 `{released:true}`로 답한다. bearer token은 `token_env` 참조다. 잠금 신원은 로컬 state 디렉터리에 기록하며 확실한 종료/미시작만 해제한다. 실제 authority와 VHD 연동이 없는 현재 환경에서는 안전하게 blocked다.

VHD jobs API도 시작 전에 두 번 읽는다. 별도 운영 격리를 명시 승인한 경우에만 PC 로컬 설정에 `allow_uncoordinated_vhd_snapshot:true`를 넣어 durable lock 없이 조회 방식으로 실행할 수 있다. 이 opt-out은 원자적 공용 잠금을 제공하지 않으며 외부 VHD 시작과의 경합이 남는다. 기본값은 false이고 웹 요청/profile로 변경할 수 없다.

Windows 세션·예약 작업 기준은 Microsoft의 [WTSINFOEX_LEVEL1](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ns-wtsapi32-wtsinfoex_level1_w)과 [New-ScheduledTaskPrincipal](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal)을 따른다.

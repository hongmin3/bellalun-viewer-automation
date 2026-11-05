# -*- coding: utf-8 -*-
"""XIPL 실행 차단 점검(core.preflight.check_xipl) — REQ-REGRESSION-001, REQ-QA-005.

기준은 그대로다: XIPL.SERVER 프로세스가 있고 9784 포트에서 수신 중이어야 한다.
2026-11-05 시험 PC에서 OS의 TCP 표가 수신 소켓 상태를 CLOSED·FIN_WAIT_1이나
정의 밖 값(0)으로 돌려줘 `-State Listen` 조회가 실제 수신 소켓을 놓쳤다. 상태값 대신
수신 소켓 모양(원격 포트 0)·소유 PID·실제 TCP 접속으로 같은 기준을 확인한다.
"""

import socket
import unittest
from unittest.mock import patch

from core import preflight


def _fake_ps(pids, rows, broken_state=True):
    """Get-Process/Get-NetTCPConnection 응답 흉내. rows: (주소, 원격포트, PID)."""
    def ps(script):
        if "Get-Process" in script:
            return "\n".join(str(p) for p in pids)
        if "Get-NetTCPConnection" in script:
            # 이 PC의 상태값으로는 Listen 필터가 아무것도 돌려주지 않았다.
            if broken_state and "-State Listen" in script:
                return ""
            return "\n".join(f"{a}|{r}|{p}" for a, r, p in rows)
        raise AssertionError(script)
    return ps


class XiplGateTest(unittest.TestCase):
    def check(self, pids, rows, accepts=True, names=("XIPL.SERVER", "XIPL.KEEPALIVE")):
        connects = []

        def connect(addr, timeout=None):
            connects.append(addr)
            if accepts is not True and addr not in (accepts or ()):
                raise ConnectionRefusedError(10061, "refused")
            return _Conn()

        with patch.object(preflight.sysinfo, "_ps", side_effect=_fake_ps(pids, rows)), \
                patch.object(preflight.sysinfo, "process_names", return_value=list(names)), \
                patch.object(preflight.socket, "create_connection", side_effect=connect):
            return preflight.check_xipl(), connects

    def test_listener_missed_by_state_filter_passes(self):
        result, connects = self.check([13988], [("127.0.0.1", 0, 13988)])
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["port_listening"])
        self.assertEqual(connects, [("127.0.0.1", 9784)])

    def test_any_address_listener_is_probed_on_loopback(self):
        result, connects = self.check([7], [("0.0.0.0", 0, 7)])
        self.assertTrue(result["ok"])
        self.assertEqual(connects, [("127.0.0.1", 9784)])

    def test_ipv6_any_listener_is_probed_on_ipv6_loopback(self):
        result, connects = self.check([7], [("::", 0, 7)])
        self.assertTrue(result["ok"])
        self.assertEqual(connects, [("::1", 9784)])

    def test_later_listener_is_tried_when_first_row_refuses(self):
        rows = [("::", 0, 7), ("127.0.0.1", 0, 7)]
        result, connects = self.check([7], rows, accepts=[("127.0.0.1", 9784)])
        self.assertTrue(result["ok"])
        self.assertEqual(connects, [("::1", 9784), ("127.0.0.1", 9784)])

    def test_process_listed_but_pid_lookup_empty_blocks(self):
        result, connects = self.check([], [("127.0.0.1", 0, 13988)])
        self.assertFalse(result["ok"])
        self.assertEqual(connects, [])

    def test_noise_lines_are_ignored(self):
        result, _ = self.check([7], [("WARNING", "x", "y"), ("127.0.0.1", 0, 7)])
        self.assertTrue(result["ok"])

    def test_process_missing_blocks(self):
        result, _ = self.check([], [], names=("XIPL.KEEPALIVE",))
        self.assertFalse(result["ok"])
        self.assertEqual(result["detail"], "XIPL.SERVER 미기동")

    def test_port_owned_by_other_process_blocks(self):
        result, connects = self.check([13988], [("127.0.0.1", 0, 4242)])
        self.assertFalse(result["ok"])
        self.assertFalse(result["port_listening"])
        self.assertIn("9784", result["detail"])
        self.assertEqual(connects, [])

    def test_only_connected_sockets_do_not_count_as_listening(self):
        # 원격 포트가 있는 행은 수신 소켓이 아니라 개별 연결이다.
        result, connects = self.check([13988], [("127.0.0.1", 51000, 13988)])
        self.assertFalse(result["ok"])
        self.assertEqual(connects, [])

    def test_socket_that_refuses_connections_blocks(self):
        result, connects = self.check([13988], [("127.0.0.1", 0, 13988)], accepts=False)
        self.assertFalse(result["ok"])
        self.assertFalse(result["port_listening"])
        self.assertEqual(connects, [("127.0.0.1", 9784)])

    def test_state_property_is_not_read(self):
        # 이 PC에서는 State 접근 자체가 열거형 변환 예외를 냈다.
        scripts = []
        def ps(script):
            scripts.append(script)
            return "13988" if "Get-Process" in script else ""

        with patch.object(preflight.sysinfo, "_ps", side_effect=ps), \
                patch.object(preflight.sysinfo, "process_names", return_value=["XIPL.SERVER"]):
            preflight.check_xipl()
        tcp = [s for s in scripts if "Get-NetTCPConnection" in s]
        self.assertTrue(tcp)
        for s in tcp:
            self.assertNotIn("State", s)


class AcceptsRealSocketTest(unittest.TestCase):
    def test_open_listener_accepts_and_closed_port_refuses(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            self.assertTrue(preflight._accepts("127.0.0.1", port))
        finally:
            server.close()
        self.assertFalse(preflight._accepts("127.0.0.1", port))


class _Conn:
    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


if __name__ == "__main__":
    unittest.main()

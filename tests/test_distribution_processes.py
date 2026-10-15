"""감시 프로세스 종료 때 그 실행의 자식만 정리하는 실제 Win32 검사."""
import importlib.util
import os
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows 전용 배포')
class ProcessLifetimeTests(unittest.TestCase):
    def test_closing_guard_job_terminates_its_worker(self):
        self.assertIsNotNone(importlib.util.find_spec('bellalunauto.processes'))
        from bellalunauto.processes import WindowsJob
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            with WindowsJob() as job:
                job.assign(child)
                self.assertIsNone(child.poll())
            self.assertIsNotNone(child.wait(timeout=5))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()

"""Windows 파일 이동·교체에서 잠금 관련 오류만 제한 시간 안에 재시도한다."""
import os
import time


def replace_metadata(temporary, destination):
    """작성 완료된 같은 임시 파일을 같은 metadata 경로에 원자적으로 교체한다."""
    return retry_windows_file_operation(lambda: os.replace(temporary, destination))


def retry_windows_file_operation(operation, *, before_retry=None):
    deadline = time.monotonic() + 2.0
    while True:
        try:
            return operation()
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33}:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(.05, remaining))
            if before_retry is not None:
                before_retry()
                if time.monotonic() >= deadline:
                    raise

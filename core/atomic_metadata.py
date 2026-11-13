"""Windows metadata 교체의 일시적인 읽기 핸들 충돌만 유한 재시도한다."""
import os
import time


def replace_metadata(temporary, destination):
    """작성 완료된 같은 임시 파일을 같은 metadata 경로에 원자적으로 교체한다."""
    deadline = time.monotonic() + 2.0
    while True:
        try:
            return os.replace(temporary, destination)
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in {5, 32, 33}:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(.05, remaining))

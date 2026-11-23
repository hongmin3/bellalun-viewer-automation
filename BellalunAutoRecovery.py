"""Python 설치 없이 중단된 BellalunAuto 실행을 복구하는 진입점."""
from pathlib import Path
import os

from bellalunauto.recovery_gui import launch_recovery


if __name__ == "__main__":
    workspace = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "BellalunAuto" / "작업"
    launch_recovery(workspace)

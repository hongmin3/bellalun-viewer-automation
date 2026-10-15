# -*- coding: utf-8 -*-
"""기존 전체 회귀 명령을 BellalunAuto의 공통 외부 감시로 전달한다."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def launch_arguments(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--workspace")
    options, remaining = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    config = Path(options.config).expanduser().resolve()
    # Preserve the source wrapper's historical config-directory output location.
    workspace = Path(options.workspace).expanduser().resolve() if options.workspace else config.parent
    return ["--workspace", str(workspace), "--config", str(config), "run-regression"] + remaining


def main(argv=None):
    from bellalunauto.app import main as launch
    return launch(launch_arguments(argv))


if __name__ == "__main__":
    sys.exit(main())

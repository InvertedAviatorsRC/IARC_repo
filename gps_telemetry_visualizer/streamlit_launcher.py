from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource_path(relative_path: str | Path) -> Path:
    relative = Path(relative_path)
    candidates: list[Path] = []

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / relative)

    package_root = Path(__file__).resolve().parent
    candidates.extend(
        [
            package_root / relative.name,
            package_root.parent / relative,
            Path.cwd() / relative,
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def main() -> None:
    app_path = _resource_path(Path("gps_telemetry_visualizer") / "ui.py")
    if not app_path.exists():
        raise FileNotFoundError(f"Could not locate Streamlit app at {app_path}")

    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "false")

    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    streamlit_cli.main()

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from gps_telemetry_visualizer.core import (
    OverlayLayout,
    default_overlay_layout,
    overlay_layout_from_dict,
    overlay_layout_to_dict,
)


PRESET_FILE_VERSION = 2


@dataclass
class LayoutPreset:
    name: str
    output_width: int
    output_height: int
    layout: OverlayLayout
    version: int = PRESET_FILE_VERSION


def preset_file_path() -> Path:
    return _config_dir() / "layout_presets.json"


def load_layout_presets(path: Path | None = None) -> dict[str, LayoutPreset]:
    path = path or preset_file_path()
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}

    items = raw.get("presets", raw if isinstance(raw, dict) else {})
    if not isinstance(items, dict):
        return {}

    presets = {}
    for name, value in items.items():
        if not isinstance(value, dict):
            continue
        preset_name = str(value.get("name") or name).strip()
        if not preset_name:
            continue
        width = _positive_int(value.get("output_width"), 1920)
        height = _positive_int(value.get("output_height"), 1080)
        layout = overlay_layout_from_dict(value.get("layout", value), width, height, "both")
        presets[preset_name] = LayoutPreset(
            name=preset_name,
            output_width=width,
            output_height=height,
            layout=layout,
            version=_positive_int(value.get("version"), PRESET_FILE_VERSION),
        )

    return presets


def save_layout_preset(preset: LayoutPreset, path: Path | None = None) -> None:
    path = path or preset_file_path()
    presets = load_layout_presets(path)
    presets[preset.name] = preset
    _write_presets(presets, path)


def delete_layout_preset(name: str, path: Path | None = None) -> None:
    path = path or preset_file_path()
    presets = load_layout_presets(path)
    presets.pop(name, None)
    _write_presets(presets, path)


def reset_layout(width: int, height: int, export_mode: str = "both") -> OverlayLayout:
    return default_overlay_layout(width, height, export_mode)


def _write_presets(presets: dict[str, LayoutPreset], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": PRESET_FILE_VERSION,
        "presets": {
            name: {
                "version": preset.version,
                "name": preset.name,
                "output_width": int(preset.output_width),
                "output_height": int(preset.output_height),
                "layout": overlay_layout_to_dict(preset.layout),
            }
            for name, preset in sorted(presets.items())
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _config_dir() -> Path:
    app_name = "gps_telemetry_visualizer"
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / app_name
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / app_name


def sys_platform() -> str:
    import sys

    return sys.platform


def _positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed > 0 else default

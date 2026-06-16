from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_component = components.declare_component(
    "gps_layout_editor",
    path=str(Path(__file__).with_name("layout_editor_component")),
)


def layout_editor(
    image_data_url: str,
    canvas_width: int,
    canvas_height: int,
    elements: list[dict[str, Any]],
    selected: str = "map",
    key: str | None = None,
) -> dict | None:
    return _component(
        image=image_data_url,
        canvas_width=int(canvas_width),
        canvas_height=int(canvas_height),
        elements=elements,
        selected=selected,
        key=key,
        default=None,
    )

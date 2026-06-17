from __future__ import annotations

import io
import os
import subprocess
import sys
import base64
from dataclasses import replace
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd

from gps_telemetry_visualizer.core import (
    CanvasConfig,
    ElementLayout,
    OverlayLayout,
    RenderConfig,
    clone_overlay_layout,
    compute_layout_bounds,
    default_output_name,
    default_overlay_layout,
    detect_columns,
    layout_warnings,
    prepare_telemetry,
    render_animation,
    render_static_preview,
    scale_overlay_layout,
)
from gps_telemetry_visualizer.layout_component import layout_editor
from gps_telemetry_visualizer.presets import (
    LayoutPreset,
    delete_layout_preset,
    load_layout_presets,
    save_layout_preset,
)


RESOLUTION_PRESETS = {
    "3840 × 2160 — 4K UHD": (3840, 2160),
    "2560 × 1440 — 1440p": (2560, 1440),
    "1920 × 1080 — 1080p": (1920, 1080),
    "1280 × 720 — 720p": (1280, 720),
    "1080 × 1920 — vertical 1080p": (1080, 1920),
    "2160 × 3840 — vertical 4K": (2160, 3840),
    "1080 × 1080 — square": (1080, 1080),
    "Custom": None,
}


def main() -> None:
    """Launch the Streamlit app from the installed console script."""
    app_path = Path(__file__).resolve()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=False)


def run_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="GPS Telemetry Visualizer", layout="wide")
    _inject_css(st)
    _apply_pending_preset_load(st)

    st.title("GPS Telemetry Visualizer")
    create_clicked = False

    upload_col, controls_col, preview_col = st.columns([0.82, 0.95, 2.2], gap="medium")

    with upload_col:
        st.subheader("CSV")
        uploaded_file = st.file_uploader("Drag and drop CSV file", type=["csv"], label_visibility="visible")

        if uploaded_file is not None:
            st.caption("{} uploaded".format(uploaded_file.name))
            columns = _read_columns(uploaded_file)
            detected = detect_columns(columns)
        else:
            columns = []
            detected = {"gps": "GPS", "speed": "GSpd(kmh)", "heading": "Hdg(°)", "altitude": "Alt(m)"}

        st.divider()
        st.subheader("Output")
        if "output_dir" not in st.session_state:
            st.session_state.output_dir = str(Path.cwd() / "output")
        if "pending_output_dir" in st.session_state:
            st.session_state.output_dir = st.session_state.pop("pending_output_dir")

        folder_col, browse_col = st.columns([1, 0.38], vertical_alignment="bottom")
        with folder_col:
            output_dir = st.text_input("Output folder", key="output_dir")
        with browse_col:
            if st.button("Browse", use_container_width=True):
                selected_folder = _choose_output_folder(st.session_state.output_dir)
                if selected_folder:
                    st.session_state.pending_output_dir = selected_folder
                    st.rerun()
                else:
                    st.warning("No folder selected.")

        output_type = st.radio("File type", ["mp4", "mov"], horizontal=True, index=0)
        output_width, output_height = _resolution_controls(st)

    with controls_col:
        st.subheader("Settings")
        export_mode = st.radio("Output", ["both", "map", "speedometer"], horizontal=True, index=0)
        _ensure_layout_state(st, output_width, output_height, export_mode)

        gps_col = _column_select(st, "GPS column", columns, detected.get("gps") or "GPS")
        speed_col = _column_select(st, "Speed column", columns, detected.get("speed") or "GSpd(kmh)")
        heading_col = _column_select(st, "Heading column", columns, detected.get("heading") or "Hdg(°)")
        altitude_col = _column_select(st, "Altitude column", columns, detected.get("altitude") or "Alt(m)")

        unit_col_1, unit_col_2 = st.columns(2)
        with unit_col_1:
            speed_input_unit = st.selectbox("Input speed unit", ["kmh", "mph", "ms"], index=0)
        with unit_col_2:
            speed_output_unit = st.selectbox("Output speed unit", ["mph", "kmh", "ms"], index=0)

        fps_col, seconds_col = st.columns(2)
        with fps_col:
            fps = st.slider("FPS", min_value=10, max_value=60, value=30, step=5)
        with seconds_col:
            seconds_between = st.slider("Seconds between GPS points", min_value=0.2, max_value=3.0, value=1.0, step=0.1)

        auto_max_speed = st.checkbox("Auto max speed", value=True)
        max_speed = None if auto_max_speed else st.number_input("Max speed", min_value=1.0, value=60.0, step=5.0)

        color_row_1, color_row_2 = st.columns(2)
        with color_row_1:
            path_color = st.color_picker("Path", "#00d5ff")
            speedometer_color = st.color_picker("Speedometer", "#00d5ff")
            start_marker_color = st.color_picker("Start star", "#ffd43b")
        with color_row_2:
            dot_color = st.color_picker("Position dot", "#ff3355")
            needle_color = st.color_picker("Needle", "#ff3355")

        transparent = st.checkbox(
            "Transparent background",
            value=(output_type == "mov"),
            disabled=(output_type == "mp4"),
            help="Transparent backgrounds are only available for MOV exports.",
        )
        transparent = transparent and output_type == "mov"
        background_color = "#101820"
        if not transparent:
            background_color = st.color_picker("Background", background_color)

        output_name = st.text_input("Output file name", value=default_output_name(export_mode, output_type))
        _preset_controls(st, output_width, output_height, export_mode)

        base_config = RenderConfig(
            export_mode=export_mode,
            fps=fps,
            seconds_between_gps_points=seconds_between,
            gps_col=gps_col,
            speed_col=speed_col,
            heading_col=heading_col,
            altitude_col=altitude_col,
            speed_input_unit=speed_input_unit,
            speed_output_unit=speed_output_unit,
            max_speed=max_speed,
            path_color=path_color,
            dot_color=dot_color,
            start_marker_color=start_marker_color,
            speedometer_color=speedometer_color,
            needle_color=needle_color,
            background_color=background_color,
            transparent=transparent,
            output_width=output_width,
            output_height=output_height,
            layout=clone_overlay_layout(st.session_state.overlay_layout),
        )

    config = base_config

    with preview_col:
        st.markdown('<div class="preview-heading">Preview</div>', unsafe_allow_html=True)
        preview_slot = st.empty()

        if uploaded_file is None:
            preview_slot.info("Upload a CSV to preview the map and speedometer.")
            create_clicked = st.button("Create", type="primary", use_container_width=True, disabled=True)
            _show_layout_warnings(st, base_config)
            _layout_numeric_controls(st, output_width, output_height, export_mode)
        else:
            try:
                preview_source = _uploaded_bytes(uploaded_file)
                duration_config = replace(base_config, start_time=0.0, end_time=None)
                duration_data = prepare_telemetry(io.BytesIO(preview_source), duration_config)
                trim_start, trim_end, playhead_time = _timeline_controls(
                    st,
                    duration_data.total_duration_seconds,
                    "{}:{:.3f}".format(uploaded_file.name, duration_data.total_duration_seconds),
                )
                create_clicked = st.button("Create", type="primary", use_container_width=True)

                config = replace(base_config, start_time=trim_start, end_time=trim_end)
                data = prepare_telemetry(io.BytesIO(preview_source), config)
                preview_time = max(0.0, playhead_time - trim_start)
                fig = render_static_preview(io.BytesIO(preview_source), config, frame_time=preview_time)
                preview_image = _figure_data_url(fig)
                plt.close(fig)
                with preview_slot.container():
                    drag_result = layout_editor(
                        preview_image,
                        output_width,
                        output_height,
                        _component_elements(config),
                        selected=st.session_state.get("selected_layout_element", "map"),
                        key="layout_editor",
                    )
                if _apply_drag_result(st, drag_result):
                    st.rerun()

                st.caption(
                    "{} valid GPS rows from {} total rows. Previewing {}. Export trim: {} to {}. Max speed: {:.1f} {}.".format(
                        data.valid_rows,
                        data.source_rows,
                        _format_seconds(playhead_time),
                        _format_seconds(trim_start),
                        _format_seconds(data.end_time),
                        data.max_speed,
                        config.speed_output_unit.upper(),
                    )
                )
                _show_layout_warnings(st, config)
                _layout_numeric_controls(st, output_width, output_height, export_mode)
            except Exception as exc:
                preview_slot.error(str(exc))
                create_clicked = st.button("Create", type="primary", use_container_width=True, disabled=True)
                _layout_numeric_controls(st, output_width, output_height, export_mode)

    if create_clicked:
        if uploaded_file is None:
            st.error("Upload a CSV before creating the animation.")
            return

        try:
            output_path = Path(output_dir).expanduser() / _with_extension(output_name, output_type)
            source = _uploaded_bytes(uploaded_file)
            with st.spinner("Rendering animation..."):
                rendered = render_animation(io.BytesIO(source), output_path, config)
            st.success("Created {}".format(rendered))
        except Exception as exc:
            st.error(str(exc))


def _apply_pending_preset_load(st) -> None:
    pending = st.session_state.pop("pending_layout_preset", None)
    if not pending:
        return
    st.session_state.output_width = pending.output_width
    st.session_state.output_height = pending.output_height
    st.session_state.resolution_preset = _preset_label_for_size(pending.output_width, pending.output_height)
    st.session_state.overlay_layout = clone_overlay_layout(pending.layout)
    st.session_state.layout_canvas_width = pending.output_width
    st.session_state.layout_canvas_height = pending.output_height


def _resolution_controls(st) -> tuple[int, int]:
    st.divider()
    st.subheader("Resolution")
    if "output_width" not in st.session_state:
        st.session_state.output_width = 1920
    if "output_height" not in st.session_state:
        st.session_state.output_height = 1080
    if "resolution_preset" not in st.session_state:
        st.session_state.resolution_preset = "1920 × 1080 — 1080p"

    labels = list(RESOLUTION_PRESETS)
    preset = st.selectbox(
        "Output resolution",
        labels,
        index=labels.index(st.session_state.resolution_preset)
        if st.session_state.resolution_preset in labels
        else labels.index("Custom"),
    )
    st.session_state.resolution_preset = preset

    if RESOLUTION_PRESETS[preset] is None:
        width = int(st.number_input("Output width", min_value=1, value=int(st.session_state.output_width), step=1))
        height = int(st.number_input("Output height", min_value=1, value=int(st.session_state.output_height), step=1))
    else:
        width, height = RESOLUTION_PRESETS[preset]
        st.caption("{} × {} px".format(width, height))

    old_width = int(st.session_state.get("output_width", width))
    old_height = int(st.session_state.get("output_height", height))
    if (old_width, old_height) != (width, height) and "overlay_layout" in st.session_state:
        st.session_state.overlay_layout = scale_overlay_layout(
            st.session_state.overlay_layout,
            old_width,
            old_height,
            width,
            height,
        )
        st.session_state.layout_canvas_width = width
        st.session_state.layout_canvas_height = height

    st.session_state.output_width = width
    st.session_state.output_height = height
    return width, height


def _ensure_layout_state(st, width: int, height: int, export_mode: str) -> None:
    if "overlay_layout" not in st.session_state:
        st.session_state.overlay_layout = default_overlay_layout(width, height, export_mode)
        st.session_state.layout_canvas_width = width
        st.session_state.layout_canvas_height = height
    if "selected_layout_element" not in st.session_state:
        st.session_state.selected_layout_element = "map"


def _preset_controls(st, width: int, height: int, export_mode: str) -> None:
    st.divider()
    st.subheader("Layout presets")
    presets = load_layout_presets()
    names = sorted(presets)
    selected = st.selectbox("Saved presets", [""] + names, format_func=lambda value: value or "Choose preset")
    preset_name = st.text_input("Preset name", value=selected or "")
    if preset_name.strip() and preset_name.strip() in presets:
        st.caption("Saving will replace the existing preset with this name.")

    load_col, save_col, delete_col = st.columns(3)
    with load_col:
        if st.button("Load", use_container_width=True, disabled=not selected):
            st.session_state.pending_layout_preset = presets[selected]
            st.rerun()
    with save_col:
        if st.button("Save", use_container_width=True, disabled=not preset_name.strip()):
            save_layout_preset(
                LayoutPreset(
                    preset_name.strip(),
                    width,
                    height,
                    clone_overlay_layout(st.session_state.overlay_layout),
                )
            )
            st.success("Saved preset {}".format(preset_name.strip()))
    with delete_col:
        if st.button("Delete", use_container_width=True, disabled=not selected):
            delete_layout_preset(selected)
            st.rerun()

    if selected and selected in presets and (presets[selected].output_width, presets[selected].output_height) != (width, height):
        st.info(
            "This preset was saved at {} × {}. Loading it will switch to that resolution.".format(
                presets[selected].output_width,
                presets[selected].output_height,
            )
        )

    if st.button("Reset entire layout", use_container_width=True):
        st.session_state.overlay_layout = default_overlay_layout(width, height, export_mode)
        st.rerun()


def _layout_numeric_controls(st, width: int, height: int, export_mode: str) -> None:
    st.markdown("#### Elements")
    defaults = default_overlay_layout(width, height, export_mode)
    labels = {
        "map": "Map",
        "speedometer": "Speedometer",
        "top_speed": "Top-speed indicator",
        "furthest_distance": "Furthest-distance indicator",
    }
    for name, label in labels.items():
        element = getattr(st.session_state.overlay_layout, name)
        default_element = getattr(defaults, name)
        with st.expander(label, expanded=name == st.session_state.get("selected_layout_element", "map")):
            visible = st.checkbox("Show {}".format(label.lower()), value=element.visible)
            x_col, y_col = st.columns(2)
            with x_col:
                x_value = st.number_input("{} X".format(label), value=float(element.x), step=1.0)
            with y_col:
                y_value = st.number_input("{} Y".format(label), value=float(element.y), step=1.0)
            reset_col, select_col = st.columns(2)
            with reset_col:
                if st.button("Reset {}".format(label), key="reset_{}".format(name), use_container_width=True):
                    setattr(
                        st.session_state.overlay_layout,
                        name,
                        ElementLayout(default_element.x, default_element.y, default_element.visible),
                    )
                    st.rerun()
            with select_col:
                if st.button("Select", key="select_{}".format(name), use_container_width=True):
                    st.session_state.selected_layout_element = name
                    st.rerun()

            if (element.x, element.y, element.visible) != (x_value, y_value, visible):
                setattr(st.session_state.overlay_layout, name, ElementLayout(float(x_value), float(y_value), bool(visible)))
                st.rerun()


def _figure_data_url(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=fig.dpi, facecolor=fig.get_facecolor(), transparent=fig.get_facecolor()[3] == 0)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "data:image/png;base64,{}".format(encoded)


def _component_elements(config: RenderConfig) -> list[dict]:
    canvas = CanvasConfig(config.output_width, config.output_height)
    bounds = compute_layout_bounds(config.layout, canvas, config)
    labels = {
        "map": "Map",
        "speedometer": "Speedometer",
        "top_speed": "Top speed",
        "furthest_distance": "Distance",
    }
    return [
        {
            "name": name,
            "label": labels[name],
            "x": box.x,
            "y": box.y,
            "width": box.width,
            "height": box.height,
            "visible": box.visible,
        }
        for name, box in bounds.items()
    ]


def _apply_drag_result(st, result: Optional[dict]) -> bool:
    if not result or result.get("element") not in {"map", "speedometer", "top_speed", "furthest_distance"}:
        return False
    name = result["element"]
    element = getattr(st.session_state.overlay_layout, name)
    x_value = float(result.get("x", element.x))
    y_value = float(result.get("y", element.y))
    if abs(element.x - x_value) < 0.5 and abs(element.y - y_value) < 0.5:
        st.session_state.selected_layout_element = name
        return False
    setattr(st.session_state.overlay_layout, name, ElementLayout(x_value, y_value, element.visible))
    st.session_state.selected_layout_element = name
    return True


def _show_layout_warnings(st, config: RenderConfig) -> None:
    warnings = layout_warnings(config.layout, CanvasConfig(config.output_width, config.output_height), config)
    for warning in warnings:
        st.warning(warning)


def _preset_label_for_size(width: int, height: int) -> str:
    for label, size in RESOLUTION_PRESETS.items():
        if size == (width, height):
            return label
    return "Custom"


def _read_columns(uploaded_file) -> list:
    uploaded_file.seek(0)
    columns = list(pd.read_csv(uploaded_file, nrows=0).columns)
    uploaded_file.seek(0)
    return columns


def _uploaded_bytes(uploaded_file) -> bytes:
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return data


def _timeline_controls(st, duration_seconds: float, timeline_id: str) -> tuple[float, Optional[float], float]:
    duration = max(0.0, float(duration_seconds))
    range_max = max(0.1, duration)
    step = _time_step(range_max)

    if st.session_state.get("timeline_id") != timeline_id:
        st.session_state.timeline_id = timeline_id
        st.session_state.preview_playhead_time = 0.0
        st.session_state.trim_start_time = 0.0
        st.session_state.trim_end_time = duration

    trim_start = _clamp_time(st.session_state.get("trim_start_time", 0.0), 0.0, range_max)
    trim_end = _clamp_time(st.session_state.get("trim_end_time", duration), 0.0, range_max)
    if trim_end <= trim_start:
        trim_start = 0.0
        trim_end = range_max
    playhead_time = _clamp_time(st.session_state.get("preview_playhead_time", trim_start), trim_start, trim_end)

    st.markdown("#### Timeline")
    playhead_time = st.slider(
        "Preview position",
        min_value=0.0,
        max_value=float(range_max),
        value=float(playhead_time),
        step=step,
        disabled=duration <= 0,
        help="Scrub the preview frame without changing the export range.",
    )
    trim_start, trim_end = st.slider(
        "Trim start / end",
        min_value=0.0,
        max_value=float(range_max),
        value=(float(trim_start), float(trim_end)),
        step=step,
        disabled=duration <= 0,
        help="Only this selected range is rendered when you click Create.",
    )

    trim_start = _clamp_time(trim_start, 0.0, range_max)
    trim_end = _clamp_time(trim_end, trim_start, range_max)
    if duration > 0 and trim_end <= trim_start:
        if trim_start + step <= range_max:
            trim_end = trim_start + step
        else:
            trim_start = max(0.0, trim_end - step)
    playhead_time = _clamp_time(playhead_time, trim_start, trim_end)

    st.session_state.preview_playhead_time = playhead_time
    st.session_state.trim_start_time = trim_start
    st.session_state.trim_end_time = trim_end

    st.caption(
        "Playhead {} | Trim {} to {}".format(
            _format_seconds(playhead_time),
            _format_seconds(trim_start),
            _format_seconds(trim_end),
        )
    )

    return trim_start, (trim_end if duration > 0 else None), playhead_time


def _clamp_time(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), float(lower)), float(upper))


def _time_step(duration_seconds: float) -> float:
    if duration_seconds <= 180:
        return 0.1
    if duration_seconds <= 900:
        return 0.5
    return 1.0


def _format_seconds(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    if minutes:
        return "{}:{:04.1f}".format(minutes, remaining)
    return "{:.1f}s".format(remaining)


def _column_select(st, label: str, columns: list, detected: str) -> str:
    if not columns:
        return st.text_input(label, value=detected)
    if detected in columns:
        index = columns.index(detected)
    else:
        index = 0
    return st.selectbox(label, columns, index=index)


def _with_extension(name: str, extension: str) -> str:
    root, ext = os.path.splitext(name.strip())
    if not root:
        root = "telemetry_output"
    return root + "." + extension.lstrip(".")


def _choose_output_folder(initial_dir: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            initialdir=str(Path(initial_dir).expanduser()),
            title="Choose output folder",
            mustexist=True,
        )
        root.destroy()
        return selected
    except Exception:
        try:
            script = 'POSIX path of (choose folder with prompt "Choose output folder")'
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""


def _inject_css(st) -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.2rem;
            max-width: min(1880px, 98vw);
            overflow-x: hidden;
        }
        [data-testid="stHorizontalBlock"],
        [data-testid="column"],
        [data-testid="stVerticalBlock"] {
            min-width: 0;
            max-width: 100%;
        }
        [data-testid="column"] {
            overflow-x: hidden;
        }
        .preview-heading {
            font-size: 1.05rem;
            font-weight: 700;
            line-height: 1.15;
            margin: 0 0 0.45rem 0;
            color: rgb(245, 248, 251);
        }
        div[data-testid="stMarkdownContainer"] h4 {
            margin-top: 0.45rem;
            margin-bottom: 0.25rem;
        }
        [data-testid="stFileUploaderDropzone"] {
            min-height: 190px;
            border-radius: 8px;
            border: 1px dashed rgba(80, 130, 180, 0.8);
            background: rgba(18, 31, 43, 0.04);
        }
        iframe[title="gps_layout_editor"] {
            width: 100%;
            overflow: hidden;
        }
        div.stButton > button {
            height: 3rem;
            border-radius: 8px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run_app()

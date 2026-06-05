from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from gps_telemetry_visualizer.core import (
    RenderConfig,
    default_output_name,
    detect_columns,
    prepare_telemetry,
    render_animation,
    render_static_preview,
)


def main() -> None:
    """Launch the Streamlit app from the installed console script."""
    app_path = Path(__file__).resolve()
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=False)


def run_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="GPS Telemetry Visualizer", layout="wide")
    _inject_css(st)

    st.title("GPS Telemetry Visualizer")

    upload_col, controls_col, preview_col = st.columns([0.92, 1.15, 1.35], gap="large")

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

    with controls_col:
        st.subheader("Settings")
        export_mode = st.radio("Output", ["both", "map", "speedometer"], horizontal=True, index=0)

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

        duration_seconds = 0.0
        if uploaded_file is not None:
            try:
                duration_source = _uploaded_bytes(uploaded_file)
                duration_config = RenderConfig(
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
                    transparent=False,
                )
                duration_seconds = prepare_telemetry(io.BytesIO(duration_source), duration_config).total_duration_seconds
            except Exception:
                duration_seconds = 0.0

        range_max = max(0.1, duration_seconds)
        time_range = st.slider(
            "Render time range",
            min_value=0.0,
            max_value=float(range_max),
            value=(0.0, float(range_max if duration_seconds <= 0 else duration_seconds)),
            step=0.1 if range_max <= 300 else 1.0,
            disabled=uploaded_file is None or duration_seconds <= 0,
        )

        color_row_1, color_row_2 = st.columns(2)
        with color_row_1:
            path_color = st.color_picker("Path", "#00d5ff")
            speedometer_color = st.color_picker("Speedometer", "#00d5ff")
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

        config = RenderConfig(
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
            speedometer_color=speedometer_color,
            needle_color=needle_color,
            background_color=background_color,
            transparent=transparent,
            start_time=float(time_range[0]) if uploaded_file is not None else 0.0,
            end_time=float(time_range[1]) if uploaded_file is not None and duration_seconds > 0 else None,
        )

        create_clicked = st.button("Create", type="primary", use_container_width=True)

    with preview_col:
        st.subheader("Preview")
        if uploaded_file is None:
            st.info("Upload a CSV to preview the map and speedometer.")
        else:
            try:
                preview_source = _uploaded_bytes(uploaded_file)
                data = prepare_telemetry(io.BytesIO(preview_source), config)
                st.caption(
                    "{} valid GPS rows from {} total rows. Max speed: {:.1f} {}.".format(
                        data.valid_rows,
                        data.source_rows,
                        data.max_speed,
                        config.speed_output_unit.upper(),
                    )
                )
                fig = render_static_preview(io.BytesIO(preview_source), config)
                st.pyplot(fig, clear_figure=True, use_container_width=True)
                plt.close(fig)
            except Exception as exc:
                st.error(str(exc))

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
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1480px;
        }
        [data-testid="stFileUploaderDropzone"] {
            min-height: 190px;
            border-radius: 8px;
            border: 1px dashed rgba(80, 130, 180, 0.8);
            background: rgba(18, 31, 43, 0.04);
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

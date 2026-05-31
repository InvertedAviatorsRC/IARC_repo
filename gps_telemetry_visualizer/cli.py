from __future__ import annotations

import argparse
from pathlib import Path

from gps_telemetry_visualizer.core import RenderConfig, render_animation


def main() -> None:
    parser = argparse.ArgumentParser(description="Render GPS telemetry animations from CSV files.")
    parser.add_argument("csv", help="Input CSV file")
    parser.add_argument("output", help="Output .mp4 or .mov file")
    parser.add_argument("--mode", choices=["map", "speedometer", "both"], default="both")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds-between-gps-points", type=float, default=1.0)
    parser.add_argument("--gps-col", default="GPS")
    parser.add_argument("--speed-col", default="GSpd(kmh)")
    parser.add_argument("--heading-col", default="Hdg(°)")
    parser.add_argument("--altitude-col", default="Alt(m)")
    parser.add_argument("--speed-input-unit", choices=["kmh", "mph", "ms"], default="kmh")
    parser.add_argument("--speed-output-unit", choices=["kmh", "mph", "ms"], default="mph")
    parser.add_argument("--max-speed", type=float)
    parser.add_argument("--path-color", default="#00d5ff")
    parser.add_argument("--dot-color", default="#ff3355")
    parser.add_argument("--speedometer-color", default="#00d5ff")
    parser.add_argument("--needle-color", default="#ff3355")
    parser.add_argument("--opaque", action="store_true", help="Render with an opaque dark background")
    args = parser.parse_args()

    config = RenderConfig(
        export_mode=args.mode,
        fps=args.fps,
        seconds_between_gps_points=args.seconds_between_gps_points,
        gps_col=args.gps_col,
        speed_col=args.speed_col,
        heading_col=args.heading_col,
        altitude_col=args.altitude_col,
        speed_input_unit=args.speed_input_unit,
        speed_output_unit=args.speed_output_unit,
        max_speed=args.max_speed,
        path_color=args.path_color,
        dot_color=args.dot_color,
        speedometer_color=args.speedometer_color,
        needle_color=args.needle_color,
        transparent=not args.opaque,
    )

    rendered = render_animation(Path(args.csv), Path(args.output), config)
    print("Created {}".format(rendered))


if __name__ == "__main__":
    main()

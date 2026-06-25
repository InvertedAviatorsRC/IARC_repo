from __future__ import annotations

from gps_telemetry_visualizer.native_speedometer_patch import install as install_native_speedometers


def main() -> None:
    install_native_speedometers()

    from gps_telemetry_visualizer import native_app

    native_app.SPEEDOMETER_STYLES.setdefault("90° corner gauge — lower left", "corner_left")
    native_app.main()


if __name__ == "__main__":
    main()

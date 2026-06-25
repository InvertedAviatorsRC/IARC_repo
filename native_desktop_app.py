from gps_telemetry_visualizer.native_speedometer_patch import install

install()

from gps_telemetry_visualizer import native_app

native_app.SPEEDOMETER_STYLES.setdefault("90° corner gauge — lower left", "corner_left")
main = native_app.main


if __name__ == "__main__":
    main()

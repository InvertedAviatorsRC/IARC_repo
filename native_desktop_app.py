from gps_telemetry_visualizer.native_speedometer_patch import extend_native_app, install

install()

from gps_telemetry_visualizer import native_app

extend_native_app(native_app)
main = native_app.main


if __name__ == "__main__":
    main()

from gps_telemetry_visualizer.native_app import main

from gps_telemetry_visualizer.native_speedometer_patch import install

install()


if __name__ == "__main__":
    main()

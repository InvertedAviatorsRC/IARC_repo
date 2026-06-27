from gps_telemetry_visualizer.native_smoothing_patch import install as install_smoothing
from gps_telemetry_visualizer.native_speedometer_text_patch import setup
from gps_telemetry_visualizer.native_colored_trail_patch import setup as setup_colored_trail
from gps_telemetry_visualizer import native_app

install_smoothing()
setup(native_app)
setup_colored_trail(native_app)
main = native_app.main


if __name__ == "__main__":
    main()

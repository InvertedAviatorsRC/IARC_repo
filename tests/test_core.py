import io
import unittest

import matplotlib.pyplot as plt

from gps_telemetry_visualizer.core import (
    RenderConfig,
    convert_speed,
    parse_gps,
    prepare_telemetry,
    render_preview_frames,
    render_static_preview,
)


class CoreTests(unittest.TestCase):
    def test_parse_gps_accepts_space_or_comma(self):
        self.assertEqual(parse_gps("44.766099 -93.331609"), (44.766099, -93.331609))
        self.assertEqual(parse_gps("44.766099,-93.331609"), (44.766099, -93.331609))

    def test_convert_speed(self):
        self.assertAlmostEqual(convert_speed(100, "kmh", "mph"), 62.137, places=3)
        self.assertAlmostEqual(convert_speed(60, "mph", "kmh"), 96.56064, places=5)

    def test_prepare_telemetry_interpolates_rows(self):
        csv_data = io.StringIO(
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,36,10,201\n"
        )
        data = prepare_telemetry(csv_data, RenderConfig(fps=10, seconds_between_gps_points=1))

        self.assertEqual(data.valid_rows, 2)
        self.assertEqual(len(data.frame_x), 11)
        self.assertEqual(data.speed_col, "GSpd(kmh)")
        self.assertAlmostEqual(data.frame_speed[-1], convert_speed(36, "kmh", "mph"))

    def test_prepare_telemetry_trims_to_requested_time_range(self):
        csv_data = io.StringIO(
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,36,10,201\n"
            "44.0002 -93.0002,72,20,202\n"
        )
        data = prepare_telemetry(
            csv_data,
            RenderConfig(fps=10, seconds_between_gps_points=1, start_time=0.5, end_time=1.5),
        )

        self.assertEqual(data.valid_rows, 3)
        self.assertAlmostEqual(data.total_duration_seconds, 2.0)
        self.assertAlmostEqual(data.start_time, 0.5)
        self.assertAlmostEqual(data.end_time, 1.5)
        self.assertEqual(len(data.frame_x), 11)
        self.assertGreater(data.frame_speed[-1], data.frame_speed[0])

    def test_render_preview_frames_returns_png_frames(self):
        csv_data = io.StringIO(
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,36,10,201\n"
        )
        frames, data = render_preview_frames(csv_data, RenderConfig(fps=10, seconds_between_gps_points=1), frame_count=3)

        self.assertEqual(len(frames), 3)
        self.assertTrue(frames[0].startswith(b"\x89PNG"))
        self.assertEqual(data.valid_rows, 2)

    def test_render_static_preview_accepts_frame_time(self):
        csv_data = io.StringIO(
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,36,10,201\n"
        )
        fig = render_static_preview(csv_data, RenderConfig(fps=10, seconds_between_gps_points=1), frame_time=0.5)

        self.assertGreater(len(fig.axes), 0)
        plt.close(fig)

    def test_render_static_preview_uses_trimmed_path(self):
        csv_text = (
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,12,10,201\n"
            "44.0002 -93.0002,24,20,202\n"
            "44.0003 -93.0003,36,30,203\n"
        )
        config = RenderConfig(
            export_mode="map",
            fps=10,
            seconds_between_gps_points=1,
            start_time=1.0,
            end_time=2.0,
        )
        data = prepare_telemetry(io.StringIO(csv_text), config)
        fig = render_static_preview(io.StringIO(csv_text), config, frame_time=99.0)

        x_data = list(fig.axes[0].lines[0].get_xdata())
        y_data = list(fig.axes[0].lines[0].get_ydata())

        self.assertEqual(len(x_data), len(data.frame_x))
        self.assertAlmostEqual(x_data[0], data.frame_x[0])
        self.assertAlmostEqual(y_data[0], data.frame_y[0])
        self.assertNotAlmostEqual(x_data[0], 0.0)
        self.assertNotAlmostEqual(y_data[0], 0.0)
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()

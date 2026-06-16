import io
import unittest

import matplotlib.pyplot as plt
import numpy as np

from gps_telemetry_visualizer.core import (
    RenderConfig,
    TelemetryData,
    compute_frame_states,
    convert_speed,
    format_distance,
    parse_gps,
    prepare_telemetry,
    render_preview_frames,
    render_static_preview,
)


def _telemetry(speeds, x_values=None, y_values=None):
    speeds = np.asarray(speeds, dtype=float)
    if x_values is None:
        x_values = np.arange(len(speeds), dtype=float)
    if y_values is None:
        y_values = np.zeros(len(speeds), dtype=float)
    x_values = np.asarray(x_values, dtype=float)
    y_values = np.asarray(y_values, dtype=float)
    return TelemetryData(
        frame_x=x_values,
        frame_y=y_values,
        frame_speed=speeds,
        frame_heading=np.zeros(len(speeds), dtype=float),
        frame_altitude=np.zeros(len(speeds), dtype=float),
        bounds=(float(x_values.min()), float(x_values.max()), float(y_values.min()), float(y_values.max())),
        max_speed=float(speeds.max()),
        source_rows=len(speeds),
        valid_rows=len(speeds),
        gps_col="GPS",
        speed_col="GSpd(kmh)",
        heading_col="Hdg(°)",
        altitude_col="Alt(m)",
        total_duration_seconds=(len(speeds) - 1) / 10,
        start_time=0.0,
        end_time=(len(speeds) - 1) / 10,
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

    def test_start_marker_uses_first_trimmed_position_and_moves_with_trim(self):
        csv_text = (
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,12,10,201\n"
            "44.0002 -93.0002,24,20,202\n"
            "44.0003 -93.0003,36,30,203\n"
        )
        first_config = RenderConfig(export_mode="map", fps=10, seconds_between_gps_points=1, start_time=1.0, end_time=2.0)
        second_config = RenderConfig(export_mode="map", fps=10, seconds_between_gps_points=1, start_time=2.0, end_time=3.0)
        first_data = prepare_telemetry(io.StringIO(csv_text), first_config)
        second_data = prepare_telemetry(io.StringIO(csv_text), second_config)
        first_fig = render_static_preview(io.StringIO(csv_text), first_config, frame_time=0.0)
        second_fig = render_static_preview(io.StringIO(csv_text), second_config, frame_time=0.0)

        first_star_x = list(first_fig.axes[0].lines[1].get_xdata())[0]
        first_star_y = list(first_fig.axes[0].lines[1].get_ydata())[0]
        second_star_x = list(second_fig.axes[0].lines[1].get_xdata())[0]

        self.assertAlmostEqual(first_star_x, first_data.frame_x[0])
        self.assertAlmostEqual(first_star_y, first_data.frame_y[0])
        self.assertAlmostEqual(second_star_x, second_data.frame_x[0])
        self.assertNotAlmostEqual(first_star_x, second_star_x)
        plt.close(first_fig)
        plt.close(second_fig)

    def test_top_speed_is_cumulative_through_frame_and_initializes_at_trim_start(self):
        states = compute_frame_states(_telemetry([8.0, 7.0, 9.5]), RenderConfig(fps=10))

        self.assertEqual(states[0].top_speed, 8.0)
        self.assertEqual(states[1].top_speed, 8.0)
        self.assertEqual(states[2].top_speed, 9.5)

    def test_speed_record_threshold_and_highlight_duration_are_deterministic(self):
        data = _telemetry([10.0, 10.2, 10.49, 10.51, 10.55, 10.55, 10.55, 10.55, 10.55, 10.55])
        states = compute_frame_states(data, RenderConfig(fps=2, speed_output_unit="mph"))

        self.assertFalse(states[1].top_speed_highlight)
        self.assertFalse(states[2].top_speed_highlight)
        self.assertTrue(states[3].top_speed_highlight)
        self.assertTrue(states[8].top_speed_highlight)
        self.assertFalse(states[9].top_speed_highlight)
        self.assertEqual(states[2].top_speed, 10.49)

    def test_distance_starts_at_zero_and_uses_trim_start_position(self):
        states = compute_frame_states(
            _telemetry([0, 0, 0], x_values=[100.0, 103.0, 100.0]),
            RenderConfig(fps=10),
        )

        self.assertEqual(states[0].current_distance_m, 0.0)
        self.assertAlmostEqual(states[1].furthest_distance_m, 3.0)
        self.assertAlmostEqual(states[2].furthest_distance_m, 3.0)

    def test_distance_record_threshold_and_highlight_duration(self):
        states = compute_frame_states(
            _telemetry([0] * 10, x_values=[0.0, 1.0, 3.0, 3.049, 3.1, 3.1, 3.1, 3.1, 3.1, 3.1]),
            RenderConfig(fps=2),
        )

        self.assertFalse(states[1].distance_highlight)
        self.assertFalse(states[2].distance_highlight)
        self.assertTrue(states[3].distance_highlight)
        self.assertTrue(states[8].distance_highlight)
        self.assertFalse(states[9].distance_highlight)

    def test_scrubbing_backward_frame_states_restore_earlier_records(self):
        states = compute_frame_states(_telemetry([5.0, 8.0, 6.0], x_values=[0.0, 5.0, 2.0]), RenderConfig(fps=10))

        self.assertEqual(states[1].top_speed, 8.0)
        self.assertEqual(states[1].furthest_distance_m, 5.0)
        self.assertEqual(states[0].top_speed, 5.0)
        self.assertEqual(states[0].furthest_distance_m, 0.0)

    def test_distance_formatting_switches_units(self):
        self.assertEqual(format_distance(256.641, "mph"), "842 FT")
        self.assertEqual(format_distance(377.952, "mph"), "1,240 FT")
        self.assertEqual(format_distance(2092.147, "mph"), "1.3 MI")
        self.assertEqual(format_distance(620, "kmh"), "620 M")
        self.assertEqual(format_distance(1400, "ms"), "1.4 KM")

    def test_static_preview_modes_render_with_transparency(self):
        csv_text = (
            "GPS,GSpd(kmh),Hdg(°),Alt(m)\n"
            "44.0 -93.0,0,0,200\n"
            "44.0001 -93.0001,36,10,201\n"
        )
        for mode in ("map", "speedometer", "both"):
            fig = render_static_preview(
                io.StringIO(csv_text),
                RenderConfig(export_mode=mode, fps=10, seconds_between_gps_points=1, transparent=True),
                frame_time=0.5,
            )
            self.assertGreater(len(fig.axes), 0)
            self.assertEqual(fig.get_facecolor()[3], 0)
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()

import io
import unittest

from gps_telemetry_visualizer.core import RenderConfig, convert_speed, parse_gps, prepare_telemetry


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


if __name__ == "__main__":
    unittest.main()

import unittest

from src.utils.game_viewport import ViewportRect, centered_aspect_crop


class CenteredAspectCropTests(unittest.TestCase):
    def test_keeps_16_by_9_geometry(self):
        self.assertEqual(
            centered_aspect_crop((10, 20, 1920, 1080)),
            ViewportRect(10, 20, 1920, 1080),
        )

    def test_centers_16_by_9_inside_2560_by_1080(self):
        self.assertEqual(
            centered_aspect_crop((0, 0, 2560, 1080)),
            ViewportRect(320, 0, 1920, 1080),
        )

    def test_centers_16_by_9_inside_3440_by_1440(self):
        self.assertEqual(
            centered_aspect_crop((0, 0, 3440, 1440)),
            ViewportRect(440, 0, 2560, 1440),
        )

    def test_centers_16_by_9_inside_3840_by_1600(self):
        self.assertEqual(
            centered_aspect_crop((100, 50, 3840, 1600)),
            ViewportRect(598, 50, 2844, 1600),
        )

    def test_centers_16_by_9_inside_tall_window(self):
        self.assertEqual(
            centered_aspect_crop((10, 20, 1600, 1200)),
            ViewportRect(10, 170, 1600, 900),
        )

    def test_rejects_empty_geometry(self):
        self.assertIsNone(centered_aspect_crop((0, 0, 0, 1080)))


if __name__ == "__main__":
    unittest.main()

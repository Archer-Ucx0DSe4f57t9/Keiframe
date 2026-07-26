import unittest

from src.fullscreen_overlay.layout import (
    rectangles_intersect,
    select_capture_geometry,
)


class FullscreenOverlayLayoutTests(unittest.TestCase):
    def test_keeps_game_viewport_when_owner_overlaps_it(self):
        viewport = (0, 0, 2560, 1440)
        owner = (700, 400, 350, 300)
        owner_screen = (0, 0, 2560, 1440)

        self.assertEqual(
            select_capture_geometry(viewport, owner, owner_screen),
            viewport,
        )

    def test_uses_owner_monitor_after_game_moves_to_another_display(self):
        viewport = (0, 0, 2560, 1440)
        owner = (-374, 425, 350, 308)
        owner_screen = (-2560, 0, 2560, 1600)

        self.assertEqual(
            select_capture_geometry(viewport, owner, owner_screen),
            owner_screen,
        )

    def test_uses_owner_monitor_for_ultrawide_black_bar(self):
        viewport = (440, 0, 2560, 1440)
        owner = (20, 300, 350, 300)
        owner_screen = (0, 0, 3440, 1440)

        self.assertEqual(
            select_capture_geometry(viewport, owner, owner_screen),
            owner_screen,
        )

    def test_falls_back_to_viewport_without_a_valid_owner_screen(self):
        viewport = (0, 0, 1920, 1080)
        owner = (3000, 200, 350, 300)

        self.assertEqual(
            select_capture_geometry(viewport, owner, None),
            viewport,
        )

    def test_edge_touching_is_not_an_intersection(self):
        self.assertFalse(
            rectangles_intersect((0, 0, 100, 100), (100, 0, 100, 100))
        )


if __name__ == "__main__":
    unittest.main()

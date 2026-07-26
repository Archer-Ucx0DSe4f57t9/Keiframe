import unittest

from src.fullscreen_overlay.protocol import decode_frame, encode_frame


class FullscreenOverlayProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        payload = encode_frame(
            {"sequence": 7, "width": 1920, "height": 1080},
            b"\x89PNG\r\n",
        )
        header, image = decode_frame(payload)

        self.assertEqual(header["version"], 1)
        self.assertEqual(header["sequence"], 7)
        self.assertEqual(header["width"], 1920)
        self.assertEqual(image, b"\x89PNG\r\n")

    def test_rejects_truncated_frame(self):
        with self.assertRaises(ValueError):
            decode_frame(b"\x01\x00\x00")

    def test_rejects_extra_bytes(self):
        payload = encode_frame({}, b"png") + b"extra"
        with self.assertRaises(ValueError):
            decode_frame(payload)


if __name__ == "__main__":
    unittest.main()

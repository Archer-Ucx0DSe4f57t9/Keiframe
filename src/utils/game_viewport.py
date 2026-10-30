from dataclasses import dataclass
from typing import Optional, Tuple


REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
REFERENCE_ASPECT_RATIO = REFERENCE_WIDTH / REFERENCE_HEIGHT


@dataclass(frozen=True)
class ViewportRect:
    """A desktop rectangle containing the active 16:9 game image."""

    x: int
    y: int
    width: int
    height: int

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height


def centered_aspect_crop(
    geometry: Tuple[int, int, int, int],
    target_aspect_ratio: float = REFERENCE_ASPECT_RATIO,
) -> Optional[ViewportRect]:
    """
    Return the largest centered rectangle with ``target_aspect_ratio``.

    StarCraft II's recognizers use a 1920x1080 coordinate system.  When a
    borderless/windowed game surface is wider than 16:9, the active viewport is
    therefore the centered 16:9 portion and the side areas must not participate
    in image recognition or overlay placement.
    """
    x, y, width, height = (int(value) for value in geometry)
    if width <= 0 or height <= 0 or target_aspect_ratio <= 0:
        return None

    current_aspect_ratio = width / float(height)
    if current_aspect_ratio > target_aspect_ratio:
        viewport_width = min(width, int(round(height * target_aspect_ratio)))
        viewport_height = height
        viewport_x = x + (width - viewport_width) // 2
        viewport_y = y
    elif current_aspect_ratio < target_aspect_ratio:
        viewport_width = width
        viewport_height = min(height, int(round(width / target_aspect_ratio)))
        viewport_x = x
        viewport_y = y + (height - viewport_height) // 2
    else:
        viewport_x = x
        viewport_y = y
        viewport_width = width
        viewport_height = height

    return ViewportRect(
        x=viewport_x,
        y=viewport_y,
        width=viewport_width,
        height=viewport_height,
    )

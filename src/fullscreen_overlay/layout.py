from typing import Optional, Tuple


Rect = Tuple[int, int, int, int]


def rectangles_intersect(first: Rect, second: Rect) -> bool:
    """Return whether two ``(x, y, width, height)`` rectangles overlap."""
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    if min(first_width, first_height, second_width, second_height) <= 0:
        return False

    return (
        first_x < second_x + second_width
        and first_x + first_width > second_x
        and first_y < second_y + second_height
        and first_y + first_height > second_y
    )


def select_capture_geometry(
    game_viewport: Rect,
    owner_geometry: Optional[Rect],
    owner_screen_geometry: Optional[Rect],
) -> Rect:
    """
    Select the desktop area used to compose the Game Bar frame.

    The game viewport remains the normal source. If the main Keiframe window
    has moved outside it—onto another monitor or an ultrawide black-bar
    region—capture its own monitor instead. Game Bar controls the final
    on-screen position, so the Qt source window does not need to overlap SC2.
    """
    if owner_geometry is None:
        return game_viewport
    if rectangles_intersect(owner_geometry, game_viewport):
        return game_viewport
    if (
        owner_screen_geometry is not None
        and rectangles_intersect(owner_geometry, owner_screen_geometry)
    ):
        return owner_screen_geometry
    return game_viewport

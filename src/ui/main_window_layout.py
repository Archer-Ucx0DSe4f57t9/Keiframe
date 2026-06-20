from PyQt5.QtWidgets import QHeaderView

from src import config


REFERENCE_MAIN_WINDOW_WIDTH = 250
TOP_CONTROL_HEIGHT = 30


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def get_control_font_size():
    return max(8, round(config.TABLE_FONT_SIZE * 0.8))


def get_table_row_height():
    return max(18, round(config.TABLE_FONT_SIZE * 1.75))


def get_top_layout_metrics(width=None, logger=None):
    width = int(width or config.MAIN_WINDOW_WIDTH)

    left_margin = max(6, round(width * 0.04))
    right_margin = max(2, round(width * 0.012))
    gap = max(3, min(8, round(width * 0.016)))

    search_width = max(44, min(90, round(width * 0.20)))
    menu_width = clamp(round(width * 0.112), 26, 34)
    drag_width = max(24, min(32, round(width * 0.10)))

    combo_width = (
        width
        - left_margin
        - right_margin
        - search_width
        - menu_width
        - drag_width
        - gap * 3
    )

    if combo_width < 70:
        if logger:
            logger.warning(
                "主窗口宽度过小，顶部控件只能压缩地图下拉框："
                f"width={width}, combo_width={combo_width}"
            )
        combo_width = max(1, combo_width)

    search_x = left_margin
    combo_x = search_x + search_width + gap
    menu_x = combo_x + combo_width + gap
    drag_x = menu_x + menu_width + gap

    last_widget_right = drag_x + drag_width
    if last_widget_right + right_margin > width and logger:
        logger.warning(
            "主窗口顶部控件可能超出窗口宽度："
            f"right={last_widget_right}, margin={right_margin}, width={width}"
        )

    menu_icon_size = clamp(
        round(min(menu_width, TOP_CONTROL_HEIGHT) * 0.64),
        16,
        22,
    )

    return {
        "width": width,
        "top_y": 5,
        "height": TOP_CONTROL_HEIGHT,
        "left_margin": left_margin,
        "right_margin": right_margin,
        "gap": gap,
        "search_x": search_x,
        "search_width": search_width,
        "combo_x": combo_x,
        "combo_width": combo_width,
        "menu_x": menu_x,
        "menu_width": menu_width,
        "menu_icon_size": menu_icon_size,
        "drag_x": drag_x,
        "drag_width": drag_width,
    }


def apply_table_row_height(table):
    row_height = get_table_row_height()
    vertical_header = table.verticalHeader()
    vertical_header.setDefaultSectionSize(row_height)
    vertical_header.setMinimumSectionSize(row_height)
    return row_height


def _table_width():
    return max(1, int(config.MAIN_WINDOW_WIDTH - config.MUTATOR_WIDTH))


def _scaled_table_width(base_width, table_width=None):
    table_width = table_width or _table_width()
    base_table_width = max(1, REFERENCE_MAIN_WINDOW_WIDTH - config.MUTATOR_WIDTH)
    return max(1, round(base_width * table_width / base_table_width))


def _set_header_modes(table, modes):
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(0)
    for column, mode in modes.items():
        header.setSectionResizeMode(column, mode)


def apply_default_table_columns(table):
    table_width = _table_width()
    table.setColumnCount(4)
    _set_header_modes(
        table,
        {
            0: QHeaderView.Fixed,
            1: QHeaderView.Stretch,
            2: QHeaderView.Fixed,
            3: QHeaderView.Fixed,
        },
    )

    time_width = _scaled_table_width(50, table_width)
    aux_width = _scaled_table_width(5, table_width)
    remaining_width = max(1, table_width - time_width - aux_width * 2)

    table.setColumnWidth(0, time_width)
    table.setColumnWidth(1, remaining_width)
    table.setColumnWidth(2, aux_width)
    table.setColumnWidth(3, aux_width)


def apply_standard_map_table_columns(table, event_width_factor, army_width_factor):
    table_width = _table_width()
    table.setColumnCount(5)
    _set_header_modes(
        table,
        {
            0: QHeaderView.Fixed,
            1: QHeaderView.Fixed,
            2: QHeaderView.Fixed,
            3: QHeaderView.Fixed,
            4: QHeaderView.Fixed,
        },
    )

    time_width = min(_scaled_table_width(40, table_width), max(1, table_width - 2))
    remaining_width = max(1, table_width - time_width)
    total_factor = max(0.01, float(event_width_factor) + float(army_width_factor))
    event_ratio = float(event_width_factor) / total_factor
    event_width = clamp(round(remaining_width * event_ratio), 1, max(1, remaining_width - 1))
    army_width = max(1, remaining_width - event_width)

    table.setColumnWidth(0, time_width)
    table.setColumnWidth(1, event_width)
    table.setColumnWidth(2, army_width)
    table.setColumnWidth(3, 0)
    table.setColumnWidth(4, 0)
    table.setColumnHidden(3, True)
    table.setColumnHidden(4, True)


def apply_malwarfare_table_columns(table):
    table_width = _table_width()
    table.setColumnCount(5)
    _set_header_modes(
        table,
        {
            0: QHeaderView.Fixed,
            1: QHeaderView.Fixed,
            2: QHeaderView.Fixed,
            3: QHeaderView.Fixed,
            4: QHeaderView.Fixed,
        },
    )

    count_width = _scaled_table_width(20, table_width)
    time_width = _scaled_table_width(40, table_width)
    fixed_width = min(count_width + time_width, max(1, table_width - 2))
    remaining_width = max(1, table_width - fixed_width)
    event_width = clamp(round(remaining_width * 0.6), 1, max(1, remaining_width - 1))
    army_width = max(1, remaining_width - event_width)

    table.setColumnWidth(0, count_width)
    table.setColumnWidth(1, time_width)
    table.setColumnWidth(2, event_width)
    table.setColumnWidth(3, army_width)
    table.setColumnWidth(4, 0)
    table.setColumnHidden(3, False)
    table.setColumnHidden(4, True)

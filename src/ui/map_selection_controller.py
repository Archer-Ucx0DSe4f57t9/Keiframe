from src import config
from src.db.map_daos import search_maps_by_keyword
from src.map_handlers import map_loader


class MapSelectionController:
    """Coordinate map search, version cycling, and automatic map selection."""

    def __init__(
        self,
        window,
        keyword_search=search_maps_by_keyword,
        map_selection_handler=map_loader.handle_map_selection,
    ):
        self.window = window
        self.keyword_search = keyword_search
        self.map_selection_handler = map_selection_handler

    def setup_search_box_connections(self, map_list):
        window = self.window

        def update_combo_box(keyword, allow_auto_select=True):
            keyword = keyword.strip().lower()
            current_selected = window.combo_box.currentText()

            window.combo_box.blockSignals(True)
            window.combo_box.clear()

            filtered = [map_name for map_name in map_list if keyword in map_name.lower()]
            mapped_results = self.keyword_search(window.maps_db, keyword)

            for map_name in reversed(mapped_results):
                if map_name in map_list and map_name not in filtered:
                    filtered.insert(0, map_name)

            window.combo_box.addItems(filtered)

            if not allow_auto_select and current_selected in filtered:
                index = window.combo_box.findText(current_selected)
                if index >= 0:
                    window.combo_box.setCurrentIndex(index)

            window.combo_box.blockSignals(False)

            if filtered and allow_auto_select:
                self.map_selection_handler(window, filtered[0])

        def filter_combo_box_user():
            keyword = window.search_box.text().strip().lower()
            update_combo_box(keyword, allow_auto_select=True)

        def filter_combo_box_clear():
            update_combo_box("", allow_auto_select=False)
            window.search_box.blockSignals(True)
            window.search_box.setText("")
            window.search_box.blockSignals(False)

        def restart_clear_timer():
            window.clear_search_timer.stop()
            window.clear_search_timer.start(30000)

        window.search_box.textChanged.connect(filter_combo_box_user)
        window.search_box.textChanged.connect(restart_clear_timer)
        window.clear_search_timer.timeout.connect(filter_combo_box_clear)
        window.combo_box.currentTextChanged.connect(window.on_map_selected)

        window.time_label.setGeometry(10, 40, 100, 20)

    def process_map_switch_logic(self):
        window = self.window
        window.logger.info(f"检测到地图切换快捷键组合: {config.MAP_SHORTCUT}")
        if window.map_version_group.isVisible():
            current_btn = None
            for btn in window.version_buttons:
                if btn.isChecked():
                    current_btn = btn
                    break

            if current_btn:
                current_idx = window.version_buttons.index(current_btn)
                next_idx = (current_idx + 1) % len(window.version_buttons)
                window.logger.info(
                    f"从版本 {current_btn.text()} 切换到版本 "
                    f"{window.version_buttons[next_idx].text()}"
                )
                window.version_buttons[next_idx].click()
        else:
            window.logger.info("当前地图不支持A/B版本切换")

    def handle_map_update(self, map_name):
        window = self.window
        window.logger.info(f"收到地图更新信号: {map_name}")
        index = window.combo_box.findText(map_name)
        if index >= 0:
            window.logger.info(f"找到地图 {map_name}，更新下拉框选择")
            window.manual_map_selection = False
            window.combo_box.setCurrentIndex(index)
            self.map_selection_handler(window, map_name)
        else:
            window.logger.warning(f"未在下拉框中找到地图: {map_name}")

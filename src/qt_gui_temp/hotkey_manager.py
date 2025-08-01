import keyboard
import config
from mainfunctions import most_recent_playerdata, get_game_screen
from image_util import capture_screen_rect
import traceback

def handle_map_switch_hotkey(self):
    """处理地图切换快捷键"""
    self.logger.info(f'检测到地图切换快捷键组合: {config.MAP_SHORTCUT}')
    # 检查当前地图是否为A/B版本
    if self.map_version_group.isVisible():
        self.logger.info('当前地图支持A/B版本切换')
        # 获取当前选中的按钮
        current_btn = None
        for btn in self.version_buttons:
            if btn.isChecked():
                current_btn = btn
                break

        # 切换到另一个版本
        if current_btn:
            current_idx = self.version_buttons.index(current_btn)
            next_idx = (current_idx + 1) % len(self.version_buttons)
            self.logger.info(f'从版本 {current_btn.text()} 切换到版本 {self.version_buttons[next_idx].text()}')
            self.version_buttons[next_idx].click()
    else:
        self.logger.info('当前地图不支持A/B版本切换')


def handle_lock_shortcut(self):
    """处理锁定快捷键"""
    self.logger.info(f'检测到锁定快捷键组合: {config.LOCK_SHORTCUT}')
    # 切换控制窗口的锁定状态
    self.control_window.is_locked = not self.control_window.is_locked
    self.control_window.update_icon()
    # 发送状态改变信号
    self.control_window.state_changed.emit(not self.control_window.is_locked)

def handle_artifact_shortcut(self):
    # 如果窗口可见，则销毁图片
    if self.artifact_window.isVisible():
        self.artifact_window.destroy_images()
        self.artifact_window.hide()
    else:
        # 获取当前选择的地图名称并显示对应的神器图片
        try:
            current_map = self.combo_box.currentText()
            if current_map:
                self.artifact_window.show_artifact(current_map, config.ARTIFACTS_IMG_OPACITY, config.ARTIFACTS_IMG_GRAY)
        except Exception as e:
            self.logger.error(f'draw artifacts layer failed: {str(e)}')
            self.logger.error(traceback.format_exc())

def handle_screenshot_hotkey(self):
    """处理截图快捷键"""
    if not config.DEBUG_SHOW_ENEMY_INFO_SQUARE:
        return

    try:
        # 使用已保存的矩形区域进行截图
        successful_captures = 0

        for rect in self.rect_screenshots:
            try:
                # 调用capture_screen_rect进行截图并保存
                save_path = image_util.capture_screen_rect(rect)
                if save_path:
                    self.logger.info(f'成功保存截图到: {save_path}')
                    successful_captures += 1
                else:
                    self.logger.warning(f'截图保存失败: {rect.x()}, {rect.y()}, {rect.width()}, {rect.height()}')
            except Exception as capture_error:
                self.logger.error(f'区域截图失败: {str(capture_error)}')
                self.logger.error(traceback.format_exc())

        if successful_captures == len(self.rect_screenshots):
            self.logger.info('所有区域截图完成')
        else:
            self.logger.warning(f'部分区域截图失败: 成功{successful_captures}/{len(self.rect_screenshots)}')
    except Exception as e:
        self.logger.error(f'截图处理失败: {str(e)}')
        self.logger.error(traceback.format_exc())
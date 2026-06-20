import os

from PyQt5.QtCore import QObject, QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import (
    QAction,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidgetAction,
)

from src import config
from src.utils.fileutil import get_resources_dir
from src.utils.font_uitils import set_font_size
from src.utils.logging_util import get_logger


DOCUMENTATION_URL = getattr(config, "README_URL", "")
COOP_WIKI_URL = getattr(config, "WIKI_URL", "")


def get_menu_font_size():
    return max(8, round(config.TABLE_FONT_SIZE * 0.8))


def get_menu_row_height(menu_font_size):
    return max(24, round(menu_font_size * 2.4))


class ArtifactMenuRow(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("artifactMenuRow")
        self.setEnabled(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)

        self.text_label = QLabel("神器提醒", self)
        self.check_label = QLabel("", self)
        self.text_label.setObjectName("artifactMenuText")
        self.check_label.setObjectName("artifactMenuCheck")
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.check_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.check_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 0, 14, 0)
        layout.setSpacing(6)
        layout.addWidget(self.text_label)
        layout.addStretch(1)
        layout.addWidget(self.check_label)

        self.setStyleSheet("""
            QPushButton#artifactMenuRow {
                background-color: transparent;
                border: none;
                padding: 0px;
                text-align: left;
            }
            QPushButton#artifactMenuRow:hover {
                background-color: rgba(80, 80, 80, 220);
            }
            QPushButton#artifactMenuRow:pressed {
                background-color: rgba(80, 80, 80, 220);
            }
            QLabel#artifactMenuText {
                color: rgb(255, 255, 255);
                background-color: transparent;
                border: none;
            }
            QLabel#artifactMenuCheck {
                color: rgb(255, 255, 255);
                background-color: transparent;
                border: none;
            }
        """)

    def apply_metrics(self, menu_font_size, row_height):
        set_font_size(self, menu_font_size)
        set_font_size(self.text_label, menu_font_size)
        set_font_size(self.check_label, menu_font_size)
        self.check_label.setFixedWidth(max(16, round(menu_font_size * 1.8)))
        self.setFixedHeight(row_height)
        self.setMinimumWidth(142)

    def set_confirmed(self, confirmed):
        self.check_label.setText("✓" if confirmed else "")


class MainWindowMenuController(QObject):
    def __init__(self, window, parent_widget, artifact_notifier=None):
        super().__init__(window)
        self.window = window
        self._artifact_notifier = artifact_notifier
        self.logger = get_logger(__name__)

        self.menu_button = QToolButton(parent_widget)
        self.menu_button.setObjectName("mainMenuButton")
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setToolTip("主菜单")
        self.menu_button.setStyleSheet(self._button_style())

        self.menu = QMenu(self.menu_button)
        self.menu.setObjectName("mainWindowMenu")

        self.artifact_menu_action = QWidgetAction(self.menu)
        self.artifact_menu_row = ArtifactMenuRow(self.menu)
        self.artifact_menu_action.setDefaultWidget(self.artifact_menu_row)

        self.settings_action = QAction("设置", self.menu)
        self.documentation_action = QAction("说明文档", self.menu)
        self.coop_wiki_action = QAction("合作 Wiki", self.menu)
        self.exit_action = QAction("退出", self.menu)

        self.menu.addAction(self.artifact_menu_action)
        self.menu.addAction(self.settings_action)
        self.menu.addSeparator()
        self.menu.addAction(self.documentation_action)
        self.menu.addAction(self.coop_wiki_action)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_action)

        self.documentation_action.setEnabled(bool(DOCUMENTATION_URL))
        self.coop_wiki_action.setEnabled(bool(COOP_WIKI_URL))

        self.apply_menu_metrics()
        self.sync_artifact_menu_state()

        self.menu.aboutToShow.connect(self._prepare_menu_to_show)
        self.artifact_menu_row.clicked.connect(self._on_artifact_menu_clicked)
        self.settings_action.triggered.connect(self.open_settings)
        self.documentation_action.triggered.connect(
            lambda: self.open_external_url(DOCUMENTATION_URL, "说明文档")
        )
        self.coop_wiki_action.triggered.connect(
            lambda: self.open_external_url(COOP_WIKI_URL, "合作 Wiki")
        )
        self.exit_action.triggered.connect(self.exit_application)

        self.menu_button.setMenu(self.menu)
        self._apply_icon()

    def apply_geometry(self, x, y, width, height, icon_size):
        self.menu_button.setGeometry(x, y, width, height)
        self.menu_button.setFixedSize(width, height)
        self.menu_button.setIconSize(QSize(icon_size, icon_size))

    def apply_menu_metrics(self):
        menu_font_size = get_menu_font_size()
        row_height = get_menu_row_height(menu_font_size)

        menu_font = self.menu.font()
        menu_font.setPixelSize(menu_font_size)
        self.menu.setFont(menu_font)

        for action in (
            self.settings_action,
            self.documentation_action,
            self.coop_wiki_action,
            self.exit_action,
        ):
            action.setFont(menu_font)

        self.artifact_menu_row.apply_metrics(menu_font_size, row_height)
        self.menu.setStyleSheet(self._menu_style(menu_font_size, row_height))
        self._sync_artifact_row_width()

    def set_artifact_notifier(self, artifact_notifier):
        self._artifact_notifier = artifact_notifier
        self.logger.info(
            f"主菜单绑定 ArtifactNotifier："
            f"is_none={artifact_notifier is None}, "
            f"id={id(artifact_notifier) if artifact_notifier is not None else None}"
        )
        self.sync_artifact_menu_state()

    def _get_artifact_notifier(self):
        return self._artifact_notifier

    def _prepare_menu_to_show(self):
        self._sync_artifact_row_width()
        self.sync_artifact_menu_state()

    def _sync_artifact_row_width(self):
        menu_width = max(self.menu.sizeHint().width(), self.artifact_menu_row.minimumWidth())
        self.artifact_menu_row.setFixedWidth(menu_width)

    def sync_artifact_menu_state(self):
        notifier = self._get_artifact_notifier()
        confirmed = False
        if notifier is not None:
            checker = getattr(notifier, "is_activation_confirmed", None)
            if callable(checker):
                confirmed = bool(checker())
        self.artifact_menu_row.set_confirmed(confirmed)

    def _on_artifact_menu_clicked(self, checked=False):
        """
        点击神器提醒菜单行：

        - 当前有勾：关闭本局神器检测，并取消勾；
        - 当前无勾：重新启用本局神器检测，并补回勾。
        """
        notifier = self._get_artifact_notifier()

        if notifier is None:
            self.logger.warning(
                "神器提醒菜单没有绑定 ArtifactNotifier。"
            )
            QTimer.singleShot(0, self.menu.close)
            return

        state_checker = getattr(
            notifier,
            "is_activation_confirmed",
            None,
        )
        state_setter = getattr(
            notifier,
            "set_manual_detection_enabled",
            None,
        )

        if not callable(state_checker) or not callable(state_setter):
            self.logger.warning(
                "ArtifactNotifier 缺少 "
                "is_activation_confirmed/"
                "set_manual_detection_enabled 接口。"
            )
            QTimer.singleShot(0, self.menu.close)
            return

        before_enabled = bool(state_checker())
        target_enabled = not before_enabled
        before_state = getattr(notifier, "_state", None)

        try:
            state_setter(target_enabled)

            after_enabled = bool(state_checker())
            after_state = getattr(notifier, "_state", None)

            self.logger.info(
                "神器提醒菜单切换完成："
                f"enabled={before_enabled}->{after_enabled}, "
                f"state={before_state}->{after_state}, "
                f"force_requested="
                f"{getattr(notifier, '_force_recovery_requested', False)}"
            )

        except Exception:
            self.logger.exception(
                "主菜单切换 ArtifactNotifier 失败。"
            )

        finally:
            # 从 ArtifactNotifier 重新读取真实状态。
            self.sync_artifact_menu_state()

            # 防止按钮残留按下状态。
            self.artifact_menu_row.setDown(False)

            # clicked 已发生在鼠标释放之后，此时关闭菜单是安全的。
            QTimer.singleShot(0, self.menu.close)
    
    def open_settings(self):
        try:
            self.window.open_settings()
        except Exception as exc:
            self.logger.error(f"打开设置窗口失败: {exc}")

    def exit_application(self):
        self.window.safe_exit()

    def open_external_url(self, url, label):
        if not url:
            self.logger.warning(f"{label} URL 为空，已跳过打开。")
            return

        try:
            opened = QDesktopServices.openUrl(QUrl(url))
        except Exception as exc:
            self.logger.error(f"打开{label}失败: {exc}")
            return

        if not opened:
            self.logger.warning(f"系统未能打开{label}: {url}")

    def _apply_icon(self):
        icons_dir = get_resources_dir("icons")
        icon_path = os.path.join(icons_dir, "main_menu.png") if icons_dir else None
        if icon_path and os.path.exists(icon_path):
            self.menu_button.setIcon(QIcon(icon_path))
            self.menu_button.setText("")
            return

        self.menu_button.setText("☰")
        self.logger.warning(
            f"主菜单图标不存在，已临时回退为文本按钮: {icon_path}"
        )

    @staticmethod
    def _button_style():
        return """
            QToolButton#mainMenuButton {
                color: rgb(220, 220, 220);
                background-color: rgba(43, 43, 43, 200);
                border: none;
                border-radius: 4px;
                padding: 0px;
            }
            QToolButton#mainMenuButton:hover {
                background-color: rgba(70, 70, 70, 210);
            }
            QToolButton#mainMenuButton:pressed {
                background-color: rgba(90, 90, 90, 220);
            }
            QToolButton#mainMenuButton::menu-indicator {
                image: none;
            }
        """

    @staticmethod
    def _menu_style(menu_font_size, row_height):
        vertical_padding = max(4, round((row_height - menu_font_size) / 2))
        return f"""
            QMenu#mainWindowMenu {{
                color: rgb(235, 235, 235);
                background-color: rgba(38, 38, 38, 245);
                border: 1px solid rgba(120, 120, 120, 120);
                padding: 4px;
            }}
            QMenu#mainWindowMenu::item {{
                padding: {vertical_padding}px 24px {vertical_padding}px 22px;
                min-width: 96px;
                background-color: transparent;
            }}
            QMenu#mainWindowMenu::item:selected {{
                background-color: rgba(80, 80, 80, 220);
            }}
            QMenu#mainWindowMenu::item:disabled {{
                color: rgba(160, 160, 160, 150);
            }}
            QMenu#mainWindowMenu::separator {{
                height: 1px;
                background: rgba(120, 120, 120, 120);
                margin: 4px 6px;
            }}
        """
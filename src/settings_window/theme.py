def build_settings_qss(font_pt=12):
    return f"""
    QWidget {{
        color: #e8e8e8;
        font-size: {font_pt}pt;
    }}

    QDialog {{
        background: transparent;
    }}

    QFrame#windowFrame {{
        background-color: rgba(8, 8, 8, 138);
        border: 1px solid rgba(255, 255, 255, 26);
        border-radius: 10px;
    }}

    QWidget#titleBar {{
        background: transparent;
        border: none;
    }}

    QLabel#titleLabel {{
        font-size: {font_pt}pt;
        font-weight: 600;
        color: #f7f7f7;
        background: transparent;
        padding-left: 2px;
    }}

    QFrame#contentArea {{
        background: transparent;
        border: none;
        border-bottom-left-radius: 10px;
        border-bottom-right-radius: 10px;
    }}

    QTabWidget::pane {{
        border: 1px solid rgba(255, 255, 255, 18);
        background-color: rgba(10, 10, 10, 139);
        border-radius: 8px;
        top: -1px;
    }}

    QTabBar::tab {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(70, 74, 84, 165),
            stop:0.45 rgba(28, 30, 36, 170),
            stop:1 rgba(12, 12, 14, 178)
        );
        color: #d7dbe5;
        border: 1px solid rgba(255, 255, 255, 20);
        padding: 5px 10px;
        min-width: 48px;
        max-width: 88px;
        min-height: 18px;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        margin-right: 2px;
    }}

    QTabBar::tab:selected {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(110, 126, 160, 182),
            stop:0.22 rgba(54, 60, 74, 186),
            stop:1 rgba(18, 18, 24, 190)
        );
        color: #ffffff;
        border-bottom-color: rgba(135, 180, 245, 120);
    }}

    QTabBar::tab:hover:!selected {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(86, 92, 108, 175),
            stop:1 rgba(24, 24, 30, 182)
        );
    }}

    QTabBar QToolButton {{
        background-color: rgba(18, 18, 18, 175);
        color: #f0f0f0;
        border: 1px solid rgba(255, 255, 255, 18);
        border-radius: 3px;
        width: 18px;
        height: 18px;
        margin-top: 2px;
        margin-bottom: 2px;
        padding: 0px;
    }}

    QTabBar QToolButton:hover {{
        background-color: rgba(68, 92, 136, 190);
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QGroupBox {{
        background-color: rgba(20, 20, 20, 116);
        border: 1px solid rgba(255, 255, 255, 18);
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: 600;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px 0 6px;
        color: #ededed;
        background: transparent;
    }}

    QLabel {{
        background: transparent;
    }}

    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QTableWidget,
    QHeaderView::section {{
        background-color: rgba(32, 32, 32, 168);
        color: #f0f0f0;
    }}

    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox {{
        border: 1px solid rgba(255, 255, 255, 28);
        border-radius: 5px;
        padding: 4px 10px 4px 10px;
        min-height: 24px;
        selection-background-color: rgba(95, 145, 220, 150);
    }}

    QLineEdit:focus,
    QSpinBox:focus,
    QDoubleSpinBox:focus,
    QComboBox:focus,
    QTableWidget:focus {{
        border: 1px solid rgba(120, 175, 245, 155);
    }}

    QComboBox QAbstractItemView {{
        background-color: rgba(22, 22, 22, 225);
        color: #f0f0f0;
        border: 1px solid rgba(255, 255, 255, 20);
        selection-background-color: rgba(86, 130, 190, 160);
        selection-color: white;
    }}

    QCheckBox {{
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 3px;
        border: 1px solid rgba(255, 255, 255, 30);
        background: rgba(30, 30, 30, 150);
    }}

    QCheckBox::indicator:checked {{
        background: rgba(88, 132, 198, 185);
        border: 1px solid rgba(140, 185, 245, 200);
    }}

    QTableWidget {{
        border: 1px solid rgba(255, 255, 255, 18);
        border-radius: 6px;
        gridline-color: rgba(255, 255, 255, 16);
        selection-background-color: rgba(75, 118, 180, 145);
        alternate-background-color: rgba(46, 46, 46, 120);
    }}

    QHeaderView::section {{
        border: none;
        border-right: 1px solid rgba(255, 255, 255, 16);
        border-bottom: 1px solid rgba(255, 255, 255, 16);
        padding: 7px;
        font-weight: 600;
        background-color: rgba(40, 40, 40, 172);
    }}

    QTableCornerButton::section {{
        background-color: rgba(40, 40, 40, 172);
        border: none;
        border-right: 1px solid rgba(255, 255, 255, 16);
        border-bottom: 1px solid rgba(255, 255, 255, 16);
    }}

    QPushButton {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(68, 68, 68, 190),
            stop:1 rgba(28, 28, 28, 198)
        );
        color: #f4f4f4;
        border: 1px solid rgba(255, 255, 255, 24);
        border-radius: 5px;
        padding: 6px 14px;
        min-height: 30px;
    }}

    QPushButton:hover {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(88, 88, 88, 205),
            stop:1 rgba(34, 34, 34, 210)
        );
    }}

    QPushButton:pressed {{
        background-color: rgba(20, 20, 20, 220);
    }}

    QPushButton#accentButton {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(96, 138, 202, 210),
            stop:1 rgba(54, 88, 148, 215)
        );
        border: 1px solid rgba(170, 205, 255, 100);
        font-weight: 600;
        min-height: 32px;
    }}

    QPushButton#accentButton:hover {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(110, 150, 215, 225),
            stop:1 rgba(60, 97, 158, 228)
        );
    }}

    QPushButton#titleMinButton {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(78, 82, 92, 235),
            stop:0.5 rgba(36, 38, 44, 240),
            stop:1 rgba(18, 18, 20, 242)
        );
        color: white;
        border: 1px solid rgba(220, 230, 255, 70);
        border-radius: 3px;
        padding: 0px;
        min-height: 20px;
        font-size: 10pt;
        font-weight: bold;
    }}

    QPushButton#titleMinButton:hover {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(102, 108, 122, 245),
            stop:1 rgba(28, 28, 34, 245)
        );
    }}

    QPushButton#titleMinButton:pressed {{
        background: rgba(20, 20, 24, 245);
    }}

    QPushButton#titleCloseButton {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(255, 146, 104, 248),
            stop:0.45 rgba(222, 82, 40, 248),
            stop:1 rgba(170, 36, 16, 248)
        );
        color: white;
        border: 1px solid rgba(255, 245, 240, 95);
        border-radius: 3px;
        padding: 0px;
        min-height: 20px;
        font-size: 10pt;
        font-weight: bold;
    }}

    QPushButton#titleCloseButton:hover {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 rgba(255, 170, 128, 252),
            stop:0.45 rgba(240, 96, 52, 252),
            stop:1 rgba(188, 42, 18, 252)
        );
    }}

    QPushButton#titleCloseButton:pressed {{
        background: rgba(150, 28, 12, 252);
    }}

    QFrame#bottomBar {{
        background: transparent;
        border: none;
    }}

        QScrollBar:vertical {{
        background: rgba(10, 10, 10, 185);
        width: 14px;
        margin: 2px 2px 2px 2px;
        border: 1px solid rgba(255, 255, 255, 18);
        border-radius: 6px;
    }}

    QScrollBar::handle:vertical {{
        background: rgba(190, 190, 190, 210);
        min-height: 36px;
        border-radius: 5px;
        border: 1px solid rgba(255, 255, 255, 35);
    }}

    QScrollBar::handle:vertical:hover {{
        background: rgba(220, 220, 220, 230);
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        background: rgba(10, 10, 10, 185);
        height: 14px;
        margin: 2px 2px 2px 2px;
        border: 1px solid rgba(255, 255, 255, 18);
        border-radius: 6px;
    }}

    QScrollBar::handle:horizontal {{
        background: rgba(190, 190, 190, 210);
        min-width: 36px;
        border-radius: 5px;
        border: 1px solid rgba(255, 255, 255, 35);
    }}

    QScrollBar::handle:horizontal:hover {{
        background: rgba(220, 220, 220, 230);
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    QToolTip {{
        background-color: rgba(20, 20, 20, 230);
        color: #f2f2f2;
        border: 1px solid rgba(255, 255, 255, 18);
        padding: 5px;
    }}
    """
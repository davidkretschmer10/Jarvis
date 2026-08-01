from __future__ import annotations


JARVIS_QSS = """
QMainWindow {
    background: #03060b;
}

QWidget {
    color: #f1f5f9;
    font-family: 'Outfit', 'Inter', 'Segoe UI', Arial, sans-serif;
    font-size: 14px;
}

QFrame#AppShell {
    background: qradialgradient(cx:0.52, cy:0.35, radius:1.1, stop:0 rgba(8, 24, 48, 0.85), stop:0.55 #030711, stop:1 #010308);
}

QFrame#LeftSidebar {
    background: #06090e;
    border-right: 1px solid rgba(255, 255, 255, 0.04);
}

QFrame#MainSurface {
    background: rgba(3, 8, 18, 0.78);
    border-radius: 8px;
    border: 1px solid rgba(14, 165, 233, 0.18);
}

QFrame#Panel {
    background: rgba(5, 12, 24, 0.56);
    border: 1px solid rgba(14, 165, 233, 0.14);
    border-radius: 8px;
}

QFrame#RightInfoPanel {
    background: rgba(3, 8, 18, 0.72);
    border: 1px solid rgba(14, 165, 233, 0.24);
    border-radius: 8px;
}

QLabel#InfoTitle {
    color: #bae6fd;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.8px;
}

QLabel#InfoBody {
    color: #94a3b8;
    font-size: 12px;
    line-height: 1.35;
}

QFrame#TopBar {
    background: transparent;
    border: none;
}

QLabel#BrandTitle {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 1.5px;
}

QLabel#BrandSubTitle,
QLabel#MutedLabel {
    color: #64748b;
    font-size: 11px;
}

QLabel#PageTitle {
    color: #e0f2fe;
    font-size: 20px;
    font-weight: 700;
}

QLabel#SectionTitle {
    color: #475569;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
}

QLabel#StatusPill {
    background: rgba(14, 165, 233, 0.08);
    border: 1px solid rgba(14, 165, 233, 0.18);
    border-radius: 12px;
    color: #38bdf8;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton {
    background: rgba(14, 165, 233, 0.85);
    border: none;
    border-radius: 10px;
    color: #ffffff;
    font-weight: 600;
    min-height: 32px;
    padding: 6px 14px;
}

QPushButton:hover {
    background: rgba(14, 165, 233, 0.95);
}

QPushButton:pressed {
    background: rgba(3, 105, 161, 0.95);
}

QPushButton#GhostButton {
    background: transparent;
    border: none;
    color: #94a3b8;
}

QPushButton#GhostButton:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #f1f5f9;
}

QPushButton#DangerButton {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.18);
    color: #fca5a5;
    border-radius: 10px;
}

QPushButton#DangerButton:hover {
    background: rgba(239, 68, 68, 0.22);
    color: #ffffff;
}

QLineEdit {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 10px;
    color: #f8fafc;
    min-height: 28px;
    padding: 6px 10px;
    selection-background-color: #0ea5e9;
}

QLineEdit:focus {
    border: 1px solid rgba(14, 165, 233, 0.3);
    background: rgba(255, 255, 255, 0.05);
}

QScrollArea {
    background: transparent;
    border: none;
}

QScrollArea#ChatTimeline {
    background: transparent;
    border: none;
}

QWidget#ChatTimelineContainer {
    background: transparent;
}

QCheckBox,
QRadioButton {
    color: #94a3b8;
    spacing: 8px;
}

QCheckBox::indicator,
QRadioButton::indicator {
    width: 14px;
    height: 14px;
}

QCheckBox::indicator:unchecked,
QRadioButton::indicator:unchecked {
    border: 1px solid rgba(255, 255, 255, 0.15);
    background: rgba(255, 255, 255, 0.04);
    border-radius: 3px;
}

QCheckBox::indicator:checked,
QRadioButton::indicator:checked {
    border: 1px solid rgba(14, 165, 233, 0.3);
    background: #0ea5e9;
    border-radius: 3px;
}

QScrollBar:vertical {
    background: transparent;
    border: none;
    width: 5px;
    margin: 2px 0 2px 0;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 2px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.12);
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

/* Custom Context Menu Styling */
QMenu {
    background-color: #0c0f16;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    padding: 4px;
}

QMenu::item {
    background-color: transparent;
    padding: 6px 20px 6px 20px;
    border-radius: 4px;
    color: #cbd5e1;
}

QMenu::item:selected {
    background-color: rgba(14, 165, 233, 0.15);
    color: #38bdf8;
}

QMenu::separator {
    height: 1px;
    background: rgba(255, 255, 255, 0.06);
    margin: 4px 0px;
}
"""

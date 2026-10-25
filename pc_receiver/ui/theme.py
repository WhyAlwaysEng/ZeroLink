"""ZeroLink Hub - Theme & Styling Definitions (Light Minimalist Edition)
Crisp white primary palette with high-contrast black typography, hairlines, and soft shading.
"""

# Palette Constants
COLOR_BG_MAIN = "#F9FAFB"
COLOR_BG_SIDEBAR = "#FFFFFF"
COLOR_BG_SURFACE = "#FFFFFF"
COLOR_BG_SURFACE_HOVER = "#F3F4F6"
COLOR_BORDER_HAIRLINE = "#E5E7EB"
COLOR_BORDER_STRONG = "#D1D5DB"

COLOR_TEXT_PRIMARY = "#111827"
COLOR_TEXT_SECONDARY = "#4B5563"
COLOR_TEXT_MUTED = "#9CA3AF"

# Global Hub Application Stylesheet
GLOBAL_APP_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLOR_BG_MAIN};
}}
QWidget {{
    color: {COLOR_TEXT_PRIMARY};
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
}}
QFrame#sidebar {{
    background-color: {COLOR_BG_SIDEBAR};
    border-right: 1px solid {COLOR_BORDER_HAIRLINE};
}}
QPushButton {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}}
QPushButton:pressed {{
    background-color: #E5E7EB;
}}
QComboBox {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}}
QComboBox:hover {{
    border-color: #9CA3AF;
}}
QComboBox::drop-down {{
    border: none;
    width: 16px;
}}
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: #F3F4F6;
    selection-color: #000000;
    border: 1px solid {COLOR_BORDER_HAIRLINE};
}}
"""

import math
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap


def create_gear_pixmap(size: int = 18, color: str = "#374151") -> QPixmap:
    """Generates a crisp, vector mechanical gear icon without font dependency."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)

    cx, cy = size / 2.0, size / 2.0
    r_outer = size * 0.46
    r_inner = size * 0.33
    r_hole = size * 0.16

    path = QPainterPath()
    teeth = 8
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a0 = i * step
        a1 = a0 + step * 0.22
        a2 = a0 + step * 0.48
        a3 = a0 + step * 0.70

        x0 = cx + r_inner * math.cos(a0)
        y0 = cy + r_inner * math.sin(a0)
        x1 = cx + r_outer * math.cos(a1)
        y1 = cy + r_outer * math.sin(a1)
        x2 = cx + r_outer * math.cos(a2)
        y2 = cy + r_outer * math.sin(a2)
        x3 = cx + r_inner * math.cos(a3)
        y3 = cy + r_inner * math.sin(a3)

        if i == 0:
            path.moveTo(x0, y0)
        else:
            path.lineTo(x0, y0)
        path.lineTo(x1, y1)
        path.lineTo(x2, y2)
        path.lineTo(x3, y3)

    path.closeSubpath()
    hole = QPainterPath()
    hole.addEllipse(QPointF(cx, cy), r_hole, r_hole)
    gear = path.subtracted(hole)
    p.drawPath(gear)
    p.end()
    return pix

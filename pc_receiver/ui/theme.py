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

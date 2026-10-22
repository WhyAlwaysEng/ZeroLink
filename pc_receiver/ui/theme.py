"""ZeroLink Hub - Theme & Styling Definitions
Central Minimalist Monochrome Palette & Reusable Stylesheets.
"""

# Palette Constants
COLOR_BG_VOID = "#000000"
COLOR_BG_SIDEBAR = "#050505"
COLOR_BG_SURFACE = "#0D0D0D"
COLOR_BG_SURFACE_HOVER = "#141414"
COLOR_BORDER_HAIRLINE = "#1A1A1A"
COLOR_BORDER_STRONG = "#282828"

COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#888888"
COLOR_TEXT_MUTED = "#555555"

# Global Hub Application Stylesheet
GLOBAL_APP_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLOR_BG_VOID};
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
    background-color: #111111;
    color: #E0E0E0;
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: #1C1C1C;
    border-color: #404040;
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background-color: #0A0A0A;
}}
QComboBox {{
    background-color: #111111;
    color: #CCCCCC;
    border: 1px solid {COLOR_BORDER_STRONG};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
}}
QComboBox:hover {{
    border-color: #404040;
}}
QComboBox::drop-down {{
    border: none;
    width: 16px;
}}
QComboBox QAbstractItemView {{
    background-color: #0A0A0A;
    color: #FFFFFF;
    selection-background-color: #222222;
    border: 1px solid {COLOR_BORDER_STRONG};
}}
"""

"""ZeroLink Hub - Reusable FlowLayout
Provides a dynamic, responsive wrapping layout that cleanly wraps buttons
onto the next row when window width is constrained (e.g. portrait streaming window).
Prevents buttons from ever being squished or text from being truncated.
"""

from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtWidgets import QLayout, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Layout that arranges child widgets horizontally and wraps them
    to new rows when the available width is exceeded.
    """

    def __init__(self, parent: QWidget = None, margin: int = 8, spacing: int = 6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def addItem(self, item):
        self.itemList.append(item)

    def count(self) -> int:
        return len(self.itemList)

    def itemAt(self, index: int):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._doLayout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _doLayout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(+margins.left(), +margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self.itemList:
            wid = item.widget()
            if wid and wid.isHidden():
                continue
            item_w = item.sizeHint().width()
            item_h = item.sizeHint().height()
            next_x = x + item_w + spacing
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + spacing
                next_x = x + item_w + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item_h)

        total_h = y + line_height - rect.y() + margins.bottom()
        return max(total_h, 32)

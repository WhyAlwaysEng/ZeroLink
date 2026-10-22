"""ZeroLink Hub - Base Module Interface
Defines the standard contract for pluggable modules in the ZeroLink ecosystem.
"""

from abc import ABC, abstractmethod
from typing import Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject, pyqtSignal


class BaseModule(QObject):
    """Abstract base class for all ZeroLink ecosystem modules."""
    
    # Signals for module lifecycle events
    status_changed = pyqtSignal(str, str)  # module_id, status_message
    state_changed = pyqtSignal(str, bool)  # module_id, is_active

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active: bool = False

    @property
    @abstractmethod
    def module_id(self) -> str:
        """Unique identifier (e.g. 'zerocast', 'zerodrop')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """User-friendly name (e.g. 'ZeroCast', 'ZeroDrop')."""
        pass

    @property
    @abstractmethod
    def icon_glyph(self) -> str:
        """Icon or emoji representing the module."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short explanation of what this module does."""
        pass

    @property
    def is_active(self) -> bool:
        """Whether the module service is currently active and listening."""
        return self._is_active

    @abstractmethod
    def start_service(self) -> bool:
        """Starts background servers, opens sockets/ports, and initializes resources."""
        pass

    @abstractmethod
    def stop_service(self) -> bool:
        """Stops background servers, closes all sockets, and frees memory completely."""
        pass

    @abstractmethod
    def get_widget(self) -> QWidget:
        """Returns the primary viewport or control widget for the Hub UI."""
        pass

"""ZeroLink Hub - Central Module Manager
Manages registration, lifecycle, state, and discovery of ecosystem modules.
"""

from typing import Dict, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from core.base_module import BaseModule


class ModuleManager(QObject):
    """Orchestrates modules, their states, and notifies UI components."""
    
    module_registered = pyqtSignal(str)     # module_id
    module_toggled = pyqtSignal(str, bool)  # module_id, is_active

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modules: Dict[str, BaseModule] = {}

    def register_module(self, module: BaseModule):
        """Registers a new module into the hub."""
        m_id = module.module_id
        self._modules[m_id] = module
        module.state_changed.connect(lambda mid, active: self.module_toggled.emit(mid, active))
        self.module_registered.emit(m_id)

    def get_module(self, module_id: str) -> Optional[BaseModule]:
        return self._modules.get(module_id)

    def get_all_modules(self) -> List[BaseModule]:
        return list(self._modules.values())

    def toggle_module(self, module_id: str, enable: bool) -> bool:
        mod = self.get_module(module_id)
        if not mod:
            return False

        if enable and not mod.is_active:
            success = mod.start_service()
            if success:
                mod._is_active = True
                self.module_toggled.emit(module_id, True)
            return success
        elif not enable and mod.is_active:
            success = mod.stop_service()
            if success:
                mod._is_active = False
                self.module_toggled.emit(module_id, False)
            return success
        return True

    def stop_all(self):
        """Shuts down all active modules gracefully on app exit."""
        for mod in self._modules.values():
            if mod.is_active:
                mod.stop_service()
                mod._is_active = False

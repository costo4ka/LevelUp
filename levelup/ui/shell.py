"""AppShell: связывает контроллер, онбординг, основное окно и оверлей."""
from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from ..application.worker import AppController
from ..config import AppConfig
from ..domain.models import Snapshot
from ..look import SpriteManifest
from .main_window import MainWindow
from .onboarding import OnboardingDialog
from .overlay import OverlayWidget


class AppShell(QObject):
    overlay_visibility_changed = pyqtSignal(bool)

    def __init__(
        self,
        app: QApplication,
        controller: AppController,
        manifest: SpriteManifest,
        config: AppConfig,
        detected_timezone: str | None,
    ):
        super().__init__()
        self.app, self.controller = app, controller
        self.manifest, self.config, self.detected_timezone = manifest, config, detected_timezone
        self.main: MainWindow | None = None
        self.overlay: OverlayWidget | None = None
        controller.ready.connect(self._on_ready)
        controller.startup_failed.connect(self._on_failed)
        app.screenAdded.connect(self._screens_changed)
        app.screenRemoved.connect(self._screens_changed)

    # ------------------------------------------------------------------ запуск
    @pyqtSlot(object)
    def _on_ready(self, snap: Snapshot) -> None:
        if not snap.onboarding_done and OnboardingDialog(self).exec() != QDialog.DialogCode.Accepted:
            self.app.quit()
            return
        self.main = MainWindow(self)
        self.overlay = OverlayWidget(self)
        self.overlay.position_committed.connect(self._save_position)
        self.main.show()
        if self.controller.snapshot.overlay_enabled:
            self.show_overlay(persist=False)
        else:
            self.overlay_visibility_changed.emit(False)

    @pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(None, "LevelUp", message)
        self.app.quit()

    # ------------------------------------------------------------------ окна
    def overlay_visible(self) -> bool:
        return self.overlay is not None and self.overlay.isVisible()

    def show_main(self) -> None:
        if self.main is None:
            return
        self.main.setWindowState((self.main.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.main.show()
        self.main.raise_()
        self.main.activateWindow()

    def show_overlay(self, persist: bool = True) -> None:
        if self.overlay is None:
            return
        self.overlay.restore_position(self.controller.snapshot)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay_visibility_changed.emit(True)
        if persist:
            self._save(True)

    def hide_overlay(self) -> None:
        """«Скрыть»: убирает виджет и возвращает основное окно, чтобы приложение не стало недоступным."""
        if self.overlay is None:
            return
        self.overlay.hide()
        self.overlay_visibility_changed.emit(False)
        self._save(False)
        self.show_main()

    def toggle_overlay(self) -> None:
        if self.overlay_visible():
            self.overlay.hide()
            self.overlay_visibility_changed.emit(False)
            self._save(False)
        else:
            self.show_overlay()

    def quit(self) -> None:
        self.app.quit()

    # ------------------------------------------------------------------ положение виджета
    def _save(self, enabled: bool) -> None:
        pos = self.overlay.pos()
        screen = self.overlay.screen()
        self.controller.save_overlay(enabled, pos.x(), pos.y(), screen.name() if screen else None)

    @pyqtSlot(int, int, str)
    def _save_position(self, x: int, y: int, screen_name: str) -> None:
        self.controller.save_overlay(self.overlay_visible(), x, y, screen_name or None)

    def _screens_changed(self, *_: object) -> None:
        """Монитор отключён или добавлен: возвращаем виджет в доступную область."""
        if self.overlay is not None and self.overlay_visible():
            self.overlay.commit_position()

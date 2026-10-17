"""Пользовательский каталог данных (отдельно от установленного приложения)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "LEVELUP_DATA_DIR"


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def db(self) -> Path:
        return self.root / "data.db"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def lock(self) -> Path:
        return self.root / "levelup.lock"

    def ensure(self) -> None:
        for directory in (self.root, self.backups, self.logs):
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_dir(cls, root: str | Path) -> "AppPaths":
        return cls(Path(root))

    @classmethod
    def default(cls) -> "AppPaths":
        """QStandardPaths.AppLocalDataLocation; для разработки можно переопределить LEVELUP_DATA_DIR."""
        override = os.environ.get(DATA_DIR_ENV)
        if override:
            return cls(Path(override))
        from PyQt6.QtCore import QStandardPaths

        location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        if not location:
            raise OSError("не удалось определить каталог данных пользователя")
        return cls(Path(location))

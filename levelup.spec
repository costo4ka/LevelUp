# -*- mode: python ; coding: utf-8 -*-
# PyInstaller, режим onedir, без UPX. Собирать на целевой ОС (Windows 10/11 x64):
#     pyinstaller levelup.spec --noconfirm --clean
from PyInstaller.utils.hooks import collect_data_files

datas = [("levelup/assets", "levelup/assets")] + collect_data_files("tzdata")

a = Analysis(
    ["run.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=["tzdata"],
    excludes=[
        "tkinter",
        "PyQt6.QtNetwork", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtSql", "PyQt6.QtSvg",
        "PyQt6.QtMultimedia", "PyQt6.QtWebEngineCore", "PyQt6.QtPdf", "PyQt6.QtBluetooth",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LevelUp",
    console=False,
    upx=False,
    icon="levelup/assets/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LevelUp")

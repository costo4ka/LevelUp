@echo off
rem Сборка поставки LevelUp на Windows 10/11 x64: PyInstaller onedir, без UPX.
rem Нужен установленный Python 3.12 x64 (python в PATH). Результат: dist\LevelUp-windows-x64.zip
setlocal
cd /d "%~dp0"

python -m venv .venv-build || exit /b 1
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip || exit /b 1
pip install -r requirements-dev.txt || exit /b 1

rem Автотесты логики, БД и интерфейса (без экрана) должны пройти до сборки
set QT_QPA_PLATFORM=offscreen
python -m pytest -q || exit /b 1
set QT_QPA_PLATFORM=

pyinstaller levelup.spec --noconfirm --clean || exit /b 1
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\LevelUp -DestinationPath dist\LevelUp-windows-x64.zip" || exit /b 1
echo.
echo Готово: dist\LevelUp-windows-x64.zip
endlocal

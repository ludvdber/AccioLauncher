@echo off
setlocal

:: Force Python 3.13 via le launcher py (PyQt6 ne supporte pas 3.14)
set PY=py -3.13

echo === Accio Launcher — Build ===
echo.

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python 3.13 introuvable.
    echo Installe-le depuis https://python.org/downloads/
    pause
    exit /b 1
)

%PY% --version
echo.

:: Installer les dependances si besoin
echo Installation des dependances...
%PY% -m pip install -r requirements.txt pyinstaller --quiet
echo.

:: Genere l'icone si elle n'existe pas
if not exist "assets\accio_launcher.ico" (
    echo [1/3] Generation de l'icone...
    %PY% build\create_icon.py
    if errorlevel 1 (
        echo ERREUR : Impossible de generer l'icone.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Icone deja presente — OK
)

echo [2/3] Build PyInstaller...
%PY% -m PyInstaller accio_launcher.spec --noconfirm
if errorlevel 1 (
    echo ERREUR : Build PyInstaller echoue.
    pause
    exit /b 1
)

echo.
echo === Build termine ! ===
echo Executable : dist\AccioLauncher.exe
echo.
pause

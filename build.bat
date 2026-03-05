@echo off
echo === Accio Launcher — Build ===
echo.

:: Genere l'icone si elle n'existe pas
if not exist "assets\accio_launcher.ico" (
    echo [1/2] Generation de l'icone...
    python build\create_icon.py
    if errorlevel 1 (
        echo ERREUR : Impossible de generer l'icone. Installez Pillow : pip install Pillow
        exit /b 1
    )
) else (
    echo [1/2] Icone deja presente — OK
)

echo [2/2] Build PyInstaller...
pyinstaller accio_launcher.spec --noconfirm
if errorlevel 1 (
    echo ERREUR : Build PyInstaller echoue.
    exit /b 1
)

echo.
echo === Build termine ! ===
echo Executable : dist\AccioLauncher.exe

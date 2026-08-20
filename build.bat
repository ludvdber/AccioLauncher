@echo off
setlocal

:: Prefere 3.14 (supporte depuis PyQt6 6.10.2 / PyInstaller 6.16), fallback 3.13 puis 3.12.
:: 3.12 est le plancher reel : `enum.StrEnum` exige 3.11, et pyproject declare >=3.12.
set PY=py -3.14
%PY% --version >nul 2>&1
if errorlevel 1 (
    set PY=py -3.13
    %PY% --version >nul 2>&1
    if errorlevel 1 (
        set PY=py -3.12
        %PY% --version >nul 2>&1
        if errorlevel 1 (
            echo ERREUR : aucun Python 3.12+ trouve.
            echo Installe-le depuis https://python.org/downloads/
            pause
            exit /b 1
        )
    )
)

echo === Accio Launcher - Build ===
%PY% --version
echo.

:: Windows refuse de remplacer un executable en cours d'execution. Sans ce test,
:: PyInstaller travaille ~40 s puis echoue a la toute derniere etape sur un
:: "PermissionError: [WinError 5] Acces refuse" qui ne nomme pas la cause.
:: Piege reel : le launcher se minimise dans la zone de notification, donc il
:: tourne souvent SANS fenetre visible.
tasklist /FI "IMAGENAME eq AccioLauncher.exe" 2>nul | find /I "AccioLauncher.exe" >nul
if not errorlevel 1 (
    echo ERREUR : AccioLauncher.exe est en cours d'execution.
    echo.
    echo   Windows ne peut pas remplacer un programme qui tourne.
    echo   Fermez le launcher, y compris son icone dans la zone de
    echo   notification en bas a droite, puis relancez ce script.
    echo.
    pause
    exit /b 1
)

:: Dependances : requirements-dev.txt et non "requirements.txt + pyinstaller".
:: L'ancienne ligne oubliait Pillow, dont depend build\create_icon.py : sur une
:: machine neuve, la generation de l'icone echouait juste apres l'installation.
echo Installation des dependances de build...
%PY% -m pip install -r requirements-dev.txt --quiet
if errorlevel 1 (
    echo ERREUR : Installation des dependances echouee.
    pause
    exit /b 1
)
echo.

:: L'icone n'est plus generee : c'est un asset de marque (7 tailles dessinees,
:: 16 a 256). La reconstruire en reduisant un PNG rendait les petites tailles
:: molles - justement celles qu'on voit dans la barre des taches.
echo [1/5] Verification de l'icone...
%PY% "build\create_icon.py"
if errorlevel 1 (
    echo ERREUR : Icone manquante ou illisible.
    pause
    exit /b 1
)

:: Un build ne doit pas partir d'un arbre casse : le lint et les tests sont
:: rapides (~20 s) au regard d'un exe publie avec une regression dedans.
echo [2/5] Lint...
%PY% -m ruff check .
if errorlevel 1 (
    echo ERREUR : Lint echoue - build interrompu.
    pause
    exit /b 1
)

echo [3/5] Tests...
%PY% -m pytest -q
if errorlevel 1 (
    echo ERREUR : Tests en echec - build interrompu.
    pause
    exit /b 1
)

:: La suite de tests tourne en offscreen, ou QFontDatabase ne voit AUCUNE
:: police systeme : Georgia (police de corps) et Segoe UI n'existent pas et Qt
:: substitue Cinzel, 22 %% plus large et 16 %% plus haute d'interligne. Les
:: mesures de mise en page y portent donc sur une autre police que celle de
:: l'utilisateur. Ce controle-ci rejoue les memes verifications sur la
:: plateforme native, ou les polices sont reelles - d'ou sa place ici, sur la
:: machine qui publie, et pas dans pytest.
echo [4/5] Geometrie avec les vraies polices...
%PY% "tools\audit_geometrie.py"
if errorlevel 1 (
    echo ERREUR : Anomalie de mise en page - build interrompu.
    pause
    exit /b 1
)

echo [5/5] Build PyInstaller...
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

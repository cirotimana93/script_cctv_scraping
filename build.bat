@echo off
echo [*] Instalando PyInstaller si no existe...
pip install pyinstaller

echo.
echo [*] Creando ejecutable para conecction_dvr.py...
echo     - Modo: OneFile (Un solo archivo .exe)
echo     - Consola: Activada (Para ver los prints)
echo.

pyinstaller --noconfirm --onefile --console --name "HikvisionDiscovery" --clean conecction_dvr.py

echo.
if exist "dist\HikvisionDiscovery.exe" (
    echo [+] Compilacion exitosa!
    echo [+] El ejecutable esta en: dist\HikvisionDiscovery.exe
) else (
    echo [!] Hubo un error durante la compilacion.
)
pause

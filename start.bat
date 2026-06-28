@echo off
title NOVELLINK
cd /d "%~dp0"
set LANIP=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi').IPAddress"`) do set LANIP=%%i
echo.
echo   ============================================
echo     NOVELLINK
echo   ============================================
echo     Telefonda (ayni Wi-Fi):  http://%LANIP%:8000
echo     Bu bilgisayarda:         http://localhost:8000
echo.
echo     Bu pencereyi acik birakin. Kapatmak icin kapatin.
echo   ============================================
echo.
echo   freewebnovel icin gercek Chrome (CDP) baslatiliyor...
echo   (Acilan Chrome penceresini KAPATMA. CF cikarsa bir kez coz.)
".venv\Scripts\python.exe" "scripts\start_chrome_cdp.py"
echo.
".venv\Scripts\python.exe" "app\server.py"
pause

@echo off
title NOVELLINK
cd /d "%~dp0"
set TSIP=
for /f "usebackq delims=" %%i in (`""C:\Program Files\Tailscale\tailscale.exe" ip -4" 2^>nul`) do set TSIP=%%i
set LANIP=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' -ErrorAction SilentlyContinue).IPAddress"`) do set LANIP=%%i
rem Tailscale MagicDNS adi -> HTTPS adresi. Cevrimdisi okuma (Service Worker +
rem Cache API) YALNIZ https:// ya da http://localhost uzerinde calisir; duz IP
rem guvenli baglam sayilmaz ve telefon hicbir bolumu cevrimdisina kaydedemez.
set TSHOST=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { $t = tailscale status --json; (ConvertFrom-Json ($t -join '')).Self.DNSName.TrimEnd('.') } catch { '' }"`) do set TSHOST=%%i
echo.
echo   ============================================
echo     NOVELLINK
echo   ============================================
if defined TSHOST (
echo     TELEFONDA BUNU KULLAN ^(cevrimdisi kayit calisir^):
echo         https://%TSHOST%
echo.
echo     Asagidakiler de acilir ama CEVRIMDISI KAYIT YAPMAZ:
) else (
echo     Tailscale HTTPS adresi bulunamadi. Kurmak icin:
echo         tailscale serve --bg 8000
echo.
echo     Su anki adresler ^(cevrimdisi kayit YAPMAZ^):
)
echo         http://%TSIP%:8000   ^(Tailscale, her yerden^)
echo         http://%LANIP%:8000   ^(ayni Wi-Fi^)
echo         http://localhost:8000   ^(bu bilgisayar^)
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

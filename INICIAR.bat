@echo off
chcp 65001 >nul
echo ==========================================
echo    GRANJA APP - Iniciando Servidor
echo ==========================================
echo.
echo Buscando IP de tu computadora...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :found
)
:found
echo Tu IP es:%IP%
echo.
echo Accede desde esta PC:    http://localhost:5000
echo Accede desde tu celular: http:%IP%:5000
echo (Ambos deben estar en la misma WiFi)
echo.
echo Presiona Ctrl+C para detener
echo ==========================================
python app.py
pause

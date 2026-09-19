@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === Запуск Streamlit...
start "streamlit" /min ".venv\Scripts\streamlit.exe" run src/fuelloop/app/dashboard.py --server.headless true --server.enableCORS false --server.enableXsrfProtection false
timeout /t 6 /nobreak >nul
echo === Запуск публичного туннеля Cloudflare...
echo === Скопируйте ссылку https://....trycloudflare.com из окна ниже и отправьте команде
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8501 --no-autoupdate --protocol http2
pause

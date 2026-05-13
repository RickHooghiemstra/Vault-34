@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d C:\Users\timme\Vault-34
echo.
echo === Pulling latest code ===
git pull origin claude/scrape-motorcycle-exhausts-FHcwH
echo.
echo === Scraping all top brands ===
C:\Users\timme\AppData\Local\Python\bin\python3.exe main.py --all-brands
echo.
pause

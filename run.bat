@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d C:\Users\timme\Vault-34-Scraper
echo.

:: Warn if .env is missing
if not exist .env (
    echo WARNING: .env not found. Descriptions will stay in Dutch.
    echo          Copy .env.example to .env and add ANTHROPIC_API_KEY to enable translation.
    echo          Or run with --skip-translate to silence this warning.
    echo.
)

echo === Pulling latest code ===
git pull origin claude/scrape-motorcycle-exhausts-FHcwH
echo.
echo === Scraping all top brands ===
C:\Users\timme\AppData\Local\Python\bin\python3.exe main.py --all-brands
echo.
pause

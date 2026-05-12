@echo off
cd /d C:\Users\timme\Vault-34
echo.
echo === Pulling latest code ===
git pull origin claude/scrape-motorcycle-exhausts-FHcwH
echo.
echo === Scraping Akrapovic ===
python main.py --brands akrapovic
echo.
pause

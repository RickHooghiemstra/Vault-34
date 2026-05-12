@echo off
cd /d C:\Users\timme\Vault-34
echo.
echo === Pulling latest code ===
git pull origin claude/scrape-motorcycle-exhausts-FHcwH
echo.
echo === Scraping all top brands ===
python main.py --all-brands
echo.
pause

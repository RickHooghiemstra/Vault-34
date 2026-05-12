@echo off
cd /d C:\Users\timme\Vault-34
echo.
echo === Pulling latest code ===
git pull origin claude/scrape-motorcycle-exhausts-FHcwH
echo.
echo === Running discovery test ===
python main.py --discover --url https://www.uitlaatstore.nl/s-k6r14-hegeht1
echo.
pause

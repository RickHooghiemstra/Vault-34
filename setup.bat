@echo off
chcp 65001 >nul
cd /d C:\Users\timme\Vault-34
echo.
echo ============================================================
echo  Vault-34 — First-time setup
echo ============================================================
echo.

:: Check Python is available
C:\Users\timme\AppData\Local\Python\bin\python3.exe --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found at expected path.
    echo        Download from https://python.org and install to:
    echo        C:\Users\timme\AppData\Local\Python\
    echo.
    pause
    exit /b 1
)
echo [OK] Python found:
C:\Users\timme\AppData\Local\Python\bin\python3.exe --version

:: Install dependencies
echo.
echo === Installing Python dependencies ===
C:\Users\timme\AppData\Local\Python\bin\python3.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

:: Create .env from example if it doesn't exist
echo.
if exist .env (
    echo [OK] .env already exists - skipping.
) else (
    copy .env.example .env >nul
    echo [CREATED] .env copied from .env.example
)

:: Remind about API key
echo.
echo ============================================================
echo  NEXT STEP: Edit .env and add your Anthropic API key
echo.
echo  Open notepad .env and set:
echo    ANTHROPIC_API_KEY=sk-ant-...
echo.
echo  Get a key at: https://console.anthropic.com/
echo.
echo  Skip translation (no key needed) with:
echo    python main.py --all-brands --skip-translate
echo ============================================================
echo.
pause

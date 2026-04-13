@echo off
echo Installing Python dependencies...
cd /d D:\x\x-scrapper
pip install -r requirements.txt

echo.
echo Creating .env file from .env.example...
if not exist .env (
    copy .env.example .env
    echo .env created — it already has your credentials
) else (
    echo .env already exists — skipping
)

echo.
echo Setting up Windows Task Scheduler to run every 30 minutes...
schtasks /create /tn "XLeadScraper" /tr "D:\x\x-scrapper\run_scraper_local.bat" /sc minute /mo 30 /ru "%USERNAME%" /f

echo.
echo Done! The scraper will now run every 30 minutes automatically.
echo To test right now, run: python run_scraper.py
echo To check logs: type D:\x\x-scrapper\scraper.log
echo To stop: schtasks /delete /tn "XLeadScraper" /f
pause

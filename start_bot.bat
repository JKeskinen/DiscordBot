@echo off
REM Start the MetrixBot in the project's virtual environment.
REM Double-click this file to start the bot detached.

SET SCRIPT_DIR=%~dp0
SET PYTHON=%SCRIPT_DIR%\.venv\Scripts\python.exe

IF NOT EXIST "%PYTHON%" (
    echo Virtual environment not found. Create it with: python -m venv .venv
    pause
    exit /b 1
)

REM Daily-digestin kellonaika (tunti ja minuutit, 24h-kello)
REM Nämä arvot viedään ympäristömuuttujina Python-sovellukselle.
REM Oletus: klo 04:00
SET DAILY_DIGEST_HOUR=4
SET DAILY_DIGEST_MINUTE=00

REM Configure capacity worker interval (seconds) and thread for alerts
REM Capacity scan + alerts: tarkistetaan oletuksena 30 minuutin välein (1800s)
REM Voit muuttaa tätä arvoa helposti tästä tiedostosta.
SET CAPACITY_CHECK_INTERVAL=1800
SET CAPACITY_THREAD_ID=1241493648080764988

REM Interval for main daemon loop (minutes). Default 120 => 2 hours
SET METRIX_INTERVAL_MINUTES=120

REM Lasketaan kapasiteettitarkistuksen väli minuuteissa näyttöä varten
SET /A CAPACITY_CHECK_MIN=%CAPACITY_CHECK_INTERVAL%/60

echo ==========================================
echo Käynnistetään MetrixBot.
echo Päivittäinen kilpailuraportti (PDGA + viikkarit + rekisteröinnit) ajetaan noin klo %DAILY_DIGEST_HOUR%:%DAILY_DIGEST_MINUTE%.
echo Kapasiteettitarkistusväli: %CAPACITY_CHECK_INTERVAL% s (%CAPACITY_CHECK_MIN% min).
echo Metrix daemon interval: %METRIX_INTERVAL_MINUTES% min.
echo ==========================================

start "MetrixBot" "%PYTHON%" "%SCRIPT_DIR%metrixbot_verifiedWorking.py" --daemon --presence --interval-minutes %METRIX_INTERVAL_MINUTES%
echo MetrixBot käynnistetty taustalle.
exit /b 0

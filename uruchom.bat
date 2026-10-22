@echo off
rem Dwuklik: raport demo. Z argumentem: raport dla gminy/powiatu, np. uruchom.bat Sopot
cd /d "%~dp0"
python -m pip install -q -e . || goto :error
if "%~1"=="" (
    python -m bdl_report --demo raport Przykladowo -o raporty
    start "" raporty\przykladowo_demo.html
) else (
    python -m bdl_report raport "%~1" -o raporty
)
pause
exit /b 0
:error
echo Nie udalo sie zainstalowac. Sprawdz, czy masz Pythona 3.10+.
pause
exit /b 1

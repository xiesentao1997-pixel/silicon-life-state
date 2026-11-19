@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if exist "%~dp0runtime\python.exe" goto portable
where py >nul 2>nul
if errorlevel 1 goto plain
py -3 -c "import sys,sqlite3;sys.exit(sys.version_info[:2] < (3,10))" >nul 2>nul
if errorlevel 1 goto plain
py -3 apps\local-service\server.py %*
goto done
:plain
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys,sqlite3;sys.exit(sys.version_info[:2] < (3,10))" >nul 2>nul
if errorlevel 1 goto missing
python apps\local-service\server.py %*
goto done
:portable
"%~dp0runtime\python.exe" apps\local-service\server.py %*
goto done
:missing
echo Silicon Life State requires Python 3.10 or newer.
echo Download official portable Python 3.14.10 from www.python.org?
echo This writes about 12 MB of download and a runtime folder next to this launcher.
echo No administrator access or system Python installation is required.
choice /C YN /N /M "Download and verify now [Y/N]? "
if errorlevel 2 goto manual
if not errorlevel 1 goto manual
call "%~dp0apps\local-service\Get-Windows-Runtime.cmd"
if errorlevel 1 goto manual
goto portable
:manual
echo Install Python from python.org, or run:
echo   winget install -e --id Python.Python.3.13
echo Then double-click Start-Windows.cmd again.
pause
exit /b 1
:done
set "sls_result=%errorlevel%"
if not "%sls_result%"=="0" pause
exit /b %sls_result%

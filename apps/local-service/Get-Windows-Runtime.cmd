@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Run only after the user has chosen the download in Start-Windows.cmd.
set "SLS_VERSION=3.14.10"
set "SLS_MACHINE=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "SLS_MACHINE=%PROCESSOR_ARCHITEW6432%"
if /I "%SLS_MACHINE%"=="ARM64" goto arm
if /I "%SLS_MACHINE%"=="AMD64" goto x64
if /I "%SLS_MACHINE%"=="x86" goto x86
echo Unsupported Windows architecture.
exit /b 1
:arm
set "SLS_ARCH=arm64"
set "SLS_HASH=bbe116bb1248820359cbf25127ac5c7794ea161869d83686cfbc9a45203ff836"
goto fetch
:x64
set "SLS_ARCH=amd64"
set "SLS_HASH=90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
goto fetch
:x86
set "SLS_ARCH=win32"
set "SLS_HASH=11a28e8c00a6d8f56b0a6164d52546133a9ed015a5b33e04536917e4fd6e306c"
:fetch
set "SLS_URL=https://www.python.org/ftp/python/%SLS_VERSION%/python-%SLS_VERSION%-embed-%SLS_ARCH%.zip"
for %%I in ("%~dp0..\..") do set "SLS_ROOT=%%~fI"
set "SLS_RUNTIME=%SLS_ROOT%\runtime"
if exist "%SLS_RUNTIME%\python.exe" exit /b 0
set "SLS_STAGE=%SLS_ROOT%\.sls-runtime-%RANDOM%-%RANDOM%-%RANDOM%"
mkdir "%SLS_STAGE%" 2>nul
if errorlevel 1 (
    echo Could not create a private staging folder. Extract the project to a writable folder.
    exit /b 1
)
set "SLS_ARCHIVE=%SLS_STAGE%\python.zip"
set "SLS_EXTRACTED=%SLS_STAGE%\files"
echo Fetching %SLS_URL%
powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri $env:SLS_URL -OutFile $env:SLS_ARCHIVE; if ((Get-FileHash -LiteralPath $env:SLS_ARCHIVE -Algorithm SHA256).Hash -ne $env:SLS_HASH) { throw 'Python.org SHA-256 mismatch' }; Expand-Archive -LiteralPath $env:SLS_ARCHIVE -DestinationPath $env:SLS_EXTRACTED"
if errorlevel 1 goto failed
"%SLS_EXTRACTED%\python.exe" -I -c "import sqlite3,hashlib,http.server;assert sqlite3.connect(':memory:').execute('SELECT 1').fetchone()==(1,)"
if errorlevel 1 goto failed
powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; [System.IO.Directory]::Move($env:SLS_EXTRACTED,$env:SLS_RUNTIME)"
if errorlevel 1 goto failed
rmdir /S /Q "%SLS_STAGE%"
echo Verified portable Python is ready.
exit /b 0
:failed
echo The runtime could not be installed. Your application data has not been touched.
rmdir /S /Q "%SLS_STAGE%"
exit /b 1

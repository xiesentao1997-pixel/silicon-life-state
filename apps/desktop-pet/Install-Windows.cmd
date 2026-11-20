@echo off
setlocal
set "SLS_PET_DIR=%LOCALAPPDATA%\SiliconLifeState\DesktopPet"
set "SLS_CSC=%SystemRoot%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%~dp0SiliconLifePet.exe" if not exist "%SLS_CSC%" (echo Windows x64 with .NET Framework 4.8 is required. & exit /b 1)
if not exist "%SLS_PET_DIR%" mkdir "%SLS_PET_DIR%" || exit /b 1
if not exist "%~dp0SiliconLifePet.exe" goto compile
copy /y "%~dp0SiliconLifePet.exe" "%SLS_PET_DIR%\" >nul || exit /b 1
goto shortcut
:compile
"%SLS_CSC%" /nologo /codepage:65001 /target:winexe /platform:x64 /optimize+ /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll /r:System.Security.dll /out:"%SLS_PET_DIR%\SiliconLifePet.exe" "%~dp0Pet.cs" || (echo Close the running pet before updating. & exit /b 1)
:shortcut
copy /y "%~dp0Uninstall-Windows.cmd" "%SLS_PET_DIR%\" >nul
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'Silicon Life State Pet.lnk')); $s.TargetPath=Join-Path $env:SLS_PET_DIR 'SiliconLifePet.exe'; $s.Save()" || exit /b 1
if /i "%~1"=="--no-start" exit /b 0
start "" "%SLS_PET_DIR%\SiliconLifePet.exe"

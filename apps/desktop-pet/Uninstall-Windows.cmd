@echo off
setlocal
set "SLS_PET_DIR=%LOCALAPPDATA%\SiliconLifeState\DesktopPet"
if not exist "%SLS_PET_DIR%\SiliconLifePet.exe" exit /b 0
echo Exit the pet in its tray menu before uninstalling.
start /wait "" "%SLS_PET_DIR%\SiliconLifePet.exe" --disconnect
if errorlevel 1 echo Service unavailable. Use Revoke all pets in the dashboard to invalidate the pairing.
del "%SLS_PET_DIR%\SiliconLifePet.exe" || exit /b 1
reg delete HKCU\Software\SiliconLifeState\DesktopPet /f >nul 2>nul
reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v SiliconLifeStatePet /f >nul 2>nul
powershell -NoProfile -NonInteractive -Command "Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Programs')) 'Silicon Life State Pet.lnk') -ErrorAction SilentlyContinue"
del "%SLS_PET_DIR%\Uninstall-Windows.cmd"

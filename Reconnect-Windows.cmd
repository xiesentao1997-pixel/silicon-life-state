@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%~dp0Start-Windows.cmd" --reconnect %*
exit /b %errorlevel%

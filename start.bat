@echo off
setlocal

call "%~dp0scripts\launchers\start.bat" %*
exit /b %ERRORLEVEL%

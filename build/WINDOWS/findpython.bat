@echo off

where python > nul 2>&1
if %ERRORLEVEL% NEQ 0 exit /B 1

where python | head -1

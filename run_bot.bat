@echo off
SETLOCAL

REM ============================================
REM Configuration
REM ============================================

REM --- Set the name of your Python script ---
SET SCRIPT_NAME=code.py

REM --- Set the Python executable ---
REM 'py -3' uses the Python 3 launcher (recommended if installed)
REM 'python' assumes python.exe is in your PATH
SET PYTHON_COMMAND=py -3
REM SET PYTHON_COMMAND=python

REM --- Delay in seconds before restarting after a crash ---
SET RESTART_DELAY_SECONDS=15

REM ============================================
REM Script Logic - Do not modify below this line
REM ============================================

REM Change directory to the location of this batch script
cd /d "%~dp0"
echo Current Directory: %CD%

REM Check if the Python script exists
IF NOT EXIST "%SCRIPT_NAME%" (
    echo ERROR: Python script '%SCRIPT_NAME%' not found in '%CD%'.
    echo Please make sure '%SCRIPT_NAME%' and this batch file are in the same directory.
    pause
    EXIT /B 1
)

:StartScriptLoop
echo [%TIME%] Starting the Python WhatsApp Bot...
echo [%TIME%] Running command: %PYTHON_COMMAND% "%SCRIPT_NAME%"
echo [%TIME%] Bot output will follow. Press Ctrl+C in this window to attempt graceful shutdown.

REM Execute the Python script
%PYTHON_COMMAND% "%SCRIPT_NAME%"
SET EXIT_CODE=%ERRORLEVEL%

echo [%TIME%] Python script '%SCRIPT_NAME%' has exited with code: %EXIT_CODE%

REM Check the exit code.
REM Exit code 0 usually means a clean exit (though our script loops internally).
REM If the Python script's signal handler works correctly, Ctrl+C might lead to a clean exit (code 0).
REM Any other code indicates an error or unexpected termination.
IF %EXIT_CODE% EQU 0 (
    echo [%TIME%] Script exited cleanly (Code 0). Assuming intentional stop or normal completion.
    echo [%TIME%] Exiting batch script.
    goto EndScript
) ELSE (
    echo [%TIME%] Script exited with error code %EXIT_CODE%.
    echo [%TIME%] Waiting for %RESTART_DELAY_SECONDS% seconds before restarting...
    REM timeout command waits for specified seconds. /nobreak prevents interruption by keypress. > nul hides timeout output.
    timeout /t %RESTART_DELAY_SECONDS% /nobreak > nul
    echo [%TIME%] Restarting script...
    echo.
    goto StartScriptLoop
)

:EndScript
echo [%TIME%] Batch script finished.
pause
ENDLOCAL
EXIT /B 0
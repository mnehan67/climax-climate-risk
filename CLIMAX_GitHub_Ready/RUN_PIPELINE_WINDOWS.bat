@echo off
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements-pipeline.txt
if errorlevel 1 goto failed
python -m pipeline.run_all %*
if errorlevel 1 goto failed
python -m unittest discover -s tests -p "test_*.py"
if errorlevel 1 goto failed
echo SUCCESS: Real data ready. Start with START_WINDOWS.bat
goto end
:failed
echo ERROR: The real pipeline did NOT finish. Keep the app labelled TEST until it succeeds.
:end
pause

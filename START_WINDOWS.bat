@echo off
cd /d "%~dp0"
py -3 server.py || python server.py
pause

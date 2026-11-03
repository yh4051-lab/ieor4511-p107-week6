@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements-stock.txt
if errorlevel 1 (
  pause
  exit /b 1
)
py -3 web\launch_stock.py
if errorlevel 1 pause

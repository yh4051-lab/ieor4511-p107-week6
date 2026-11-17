@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe -c "import cvxpy, yfinance" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements-lab.txt
  if errorlevel 1 goto error
)
.venv\Scripts\python.exe web\launch_tax_lab.py
if errorlevel 1 goto error
exit /b 0
:error
echo Setup or startup failed. Read the message above. Requires Python 3.12.
pause
exit /b 1

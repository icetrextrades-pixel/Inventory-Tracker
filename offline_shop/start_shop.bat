@echo off
cd /d "%~dp0"
py -3 app.py
if errorlevel 1 (
  echo Could not start Family Shop. Install Python 3 with Tcl/Tk support, then try again.
  pause
)

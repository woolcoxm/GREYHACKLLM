@echo off
rem GreyLLM launcher — usage: bridge.cmd [--check | --db-map | --demo | --mock]
python "%~dp0daemon\bridge.py" %*

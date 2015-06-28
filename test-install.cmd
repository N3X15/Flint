@echo off
set FLINT_ROOT=%~dp0
cd %FLINT_ROOT%
::call python flint.py --dev essentials.yml
call python flint.py --dl-only essentials.yml
pause
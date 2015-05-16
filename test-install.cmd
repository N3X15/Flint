@echo off
set FLINT_ROOT=%~dp0
cd %FLINT_ROOT=%
call python flint.py --dry-run example.yml
pause
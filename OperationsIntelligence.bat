@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
cd /d "%ROOT%"
title Operations Intelligence and Automation Platform

call :find_python
if errorlevel 1 goto :no_python

:menu
cls
echo ================================================================
echo Operations Intelligence ^& Automation Platform
echo Service Operations Command Center
echo ================================================================
echo Project root: %ROOT%
echo.
echo  1  Launch portfolio demo
echo  2  Doctor / readiness check
echo  3  Rebuild, test, and verify release
echo  4  Create redacted support export
echo  5  Open project exports
echo  A  Advanced diagnostics self-test
echo  Q  Quit
echo.
set "CHOICE="
set /p "CHOICE=Select an option: "
if /i "%CHOICE%"=="1" goto :launch
if /i "%CHOICE%"=="2" goto :doctor
if /i "%CHOICE%"=="3" goto :rebuild
if /i "%CHOICE%"=="4" goto :export
if /i "%CHOICE%"=="5" goto :open_exports
if /i "%CHOICE%"=="A" goto :diagnostic_test
if /i "%CHOICE%"=="Q" goto :eof
goto :menu

:launch
cls
echo Verifying and launching the local portfolio demo...
echo.
call :python tools\serve_demo.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Launch returned error %RC%. Review reports and diagnostics inside this project.
pause
goto :menu

:doctor
cls
echo ================================================================
echo Readiness check
echo ================================================================
call :python --version
call :python tools\serve_demo.py --check
set "VERIFY_RC=%ERRORLEVEL%"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js: not found. It is needed only for developer tests, not normal launch.
) else (
  node --version
  node --check netlify\functions\summary.mjs
)
echo.
if "%VERIFY_RC%"=="0" (
  echo Ready: production release identity passed.
) else (
  echo Error: release identity failed. Use option 3 to rebuild and retest.
)
pause
goto :menu

:rebuild
cls
echo ================================================================
echo Rebuild, test, and verify
echo ================================================================
where tsc >nul 2>nul
if errorlevel 1 (
  echo TypeScript compiler not found. Install a verified TypeScript compiler before rebuilding.
  echo The committed production bundle can still be launched with option 1 if verification passes.
  pause
  goto :menu
)
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required for the developer test suite.
  pause
  goto :menu
)
call :python tools\generate_demo_data.py
if errorlevel 1 goto :build_failed
call :python tools\build.py
if errorlevel 1 goto :build_failed
node tests\run_tests.mjs
if errorlevel 1 goto :build_failed
call :python tests\platform_foundation_test.py
if errorlevel 1 goto :build_failed
node --check netlify\functions\summary.mjs
if errorlevel 1 goto :build_failed
call :python tests\release_contract_test.py
if errorlevel 1 goto :build_failed
call :python tests\http_smoke.py
if errorlevel 1 goto :build_failed
call :python tools\verify_release.py
if errorlevel 1 goto :build_failed
echo.
echo Rebuild, analytics tests, governed platform tests, launcher contract, HTTP/RBAC smoke, function syntax, and release verification passed.
pause
goto :menu

:build_failed
echo.
echo Build or verification failed. No release gate was bypassed.
echo Review reports\test_report.json, reports\platform_foundation_test_report.json, reports\http_smoke_report.json, reports\release_contract_test_report.json, reports\verification_report.json, and diagnostics\.
pause
goto :menu

:export
cls
echo Creating a bounded, redacted, project-local support export...
call :python tools\create_support_export.py --trigger manual-launcher
if errorlevel 1 (
  echo Support export failed. Review diagnostics\server.log.
) else (
  echo Support export completed under exports\.
)
pause
goto :menu

:open_exports
if not exist "%ROOT%exports" mkdir "%ROOT%exports"
start "" "%ROOT%exports"
goto :menu

:diagnostic_test
cls
echo This runs one controlled local Critical-diagnostic capture.
echo It creates a crash capsule and bounded Export20 evidence without network or live actions.
echo.
set "ACTION="
set /p "ACTION=Action? [Y/N] "
if /i not "%ACTION%"=="Y" goto :menu
call :python tools\serve_demo.py --diagnostic-self-test
pause
goto :menu

:find_python
where py >nul 2>nul
if not errorlevel 1 (
  set "PY_MODE=PYLAUNCHER"
  exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 (
  set "PY_MODE=PYTHON"
  exit /b 0
)
exit /b 1

:python
if "%PY_MODE%"=="PYLAUNCHER" (
  py -3 %*
) else (
  python %*
)
exit /b %ERRORLEVEL%

:no_python
cls
echo Python 3 was not found.
echo Install Python 3.11 or newer, then rerun OperationsIntelligence.bat.
echo No files were changed.
pause
exit /b 1

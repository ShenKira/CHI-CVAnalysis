@echo off
chcp 65001 >nul
setlocal EnableExtensions

REM ---------------------------------------------------------------------------
REM CVAnalysis v2 build script
REM
REM Usage:
REM   build.bat                    -> build StandAlone + OneFile for 2.0.0
REM   build.bat 2.0.1              -> build another version
REM   build.bat 2.0.0 all          -> build StandAlone + OneFile
REM   build.bat 2.0.0 standalone   -> build StandAlone only
REM   build.bat 2.0.0 onefile      -> build OneFile only
REM
REM Optional:
REM   set CVANALYSIS_PYTHON=C:\path\to\env\python.exe
REM
REM The build cache lives in .\build_cache so repeated builds can reuse
REM Nuitka bytecode/dependency caches.  StandAlone is built first so a
REM usable product is available before the slower OneFile packaging.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

set "APP_VERSION=%~1"
if "%APP_VERSION%"=="" set "APP_VERSION=2.0.0"
set "APP_VERSION=%APP_VERSION: =%"
if /i "%APP_VERSION:~0,1%"=="v" set "APP_VERSION=%APP_VERSION:~1%"

if "%APP_VERSION%"=="" (
    echo [ERROR] Version cannot be empty.
    exit /b 1
)

set "BUILD_MODE=%~2"
if "%BUILD_MODE%"=="" set "BUILD_MODE=all"
if /i "%BUILD_MODE%"=="all" goto :build_mode_ok
if /i "%BUILD_MODE%"=="standalone" goto :build_mode_ok
if /i "%BUILD_MODE%"=="onefile" goto :build_mode_ok
echo [ERROR] Build mode must be all, standalone, or onefile.
exit /b 1
:build_mode_ok

set "BUILD_CACHE=%~dp0build_cache"
set "ONEFILE_OUTPUT_DIR=%~dp0CVAnalysis_OneFile_v%APP_VERSION%"
set "STANDALONE_OUTPUT_DIR=%~dp0CVAnalysis_StandAlone_v%APP_VERSION%"
set "NUITKA_CACHE_DIR=%BUILD_CACHE%"
set "ONEFILE_TEMPDIR_SPEC={TEMP}/CVAnalysis/onefile_{PID}_{TIME_US}_{RANDOM}"

if not exist "%BUILD_CACHE%" mkdir "%BUILD_CACHE%" >nul 2>&1
if not exist "%ONEFILE_OUTPUT_DIR%" mkdir "%ONEFILE_OUTPUT_DIR%" >nul 2>&1
if not exist "%STANDALONE_OUTPUT_DIR%" mkdir "%STANDALONE_OUTPUT_DIR%" >nul 2>&1

echo.
echo ========================================
echo  CVAnalysis v2 build
echo ========================================
echo [INFO] Version        : v%APP_VERSION%
echo [INFO] Build mode     : %BUILD_MODE%
echo [INFO] Build cache    : %BUILD_CACHE%
echo [INFO] OneFile output : %ONEFILE_OUTPUT_DIR%
echo [INFO] StandAlone out : %STANDALONE_OUTPUT_DIR%
echo.

REM Prefer the named Anaconda environment that contains Nuitka.  The caller can
REM override it with CVANALYSIS_PYTHON without changing this script.
set "PYTHON_EXE="
if defined CVANALYSIS_PYTHON if exist "%CVANALYSIS_PYTHON%" set "PYTHON_EXE=%CVANALYSIS_PYTHON%"
if not defined PYTHON_EXE if exist "%USERPROFILE%\.conda\envs\nuitka_pack\python.exe" set "PYTHON_EXE=%USERPROFILE%\.conda\envs\nuitka_pack\python.exe"
if not defined PYTHON_EXE if exist "%ProgramData%\anaconda3\envs\nuitka_pack\python.exe" set "PYTHON_EXE=%ProgramData%\anaconda3\envs\nuitka_pack\python.exe"
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE (
    echo [ERROR] Python was not found. Activate an environment or set CVANALYSIS_PYTHON.
    exit /b 1
)

REM Anaconda keeps DLLs such as ffi.dll in Library\bin.  Nuitka's dependency
REM walker needs that directory on PATH, otherwise _ctypes.pyd is packaged
REM without ffi.dll and NumPy aborts while importing ctypes.
for %%I in ("%PYTHON_EXE%") do set "PYTHON_ENV=%%~dpI"
set "PYTHON_ENV=%PYTHON_ENV:~0,-1%"
set "PATH=%PYTHON_ENV%;%PYTHON_ENV%\Library\mingw-w64\bin;%PYTHON_ENV%\Library\usr\bin;%PYTHON_ENV%\Library\bin;%PYTHON_ENV%\Scripts;%PYTHON_ENV%\bin;%PATH%"

echo [INFO] Python         : %PYTHON_EXE%
echo [INFO] Python env     : %PYTHON_ENV%
"%PYTHON_EXE%" -c "import nuitka, PySide6, numpy, scipy, pandas, matplotlib"
if errorlevel 1 (
    echo [ERROR] Missing Nuitka or project dependencies in the selected environment.
    echo         Expected: nuitka PySide6 numpy scipy pandas matplotlib
    exit /b 1
)
"%PYTHON_EXE%" -m nuitka --version
if errorlevel 1 (
    echo [ERROR] Nuitka is not runnable with the selected Python.
    exit /b 1
)

REM Use MSVC and version resources. Avoid compression/UPX-style heuristics in
REM the OneFile payload; the StandAlone folder remains the safer deployment.
set "COMMON_OPTIONS=--enable-plugin=pyside6 --include-package=cvanalysis --include-module=socket --nofollow-import-to=pandas.tests --nofollow-import-to=scipy.tests --nofollow-import-to=matplotlib.tests --windows-console-mode=disable --assume-yes-for-downloads --msvc=latest --lto=no --company-name=CVAnalysis --product-name=CVAnalysis --file-description="CVAnalysis electrochemical data analysis" --file-version=%APP_VERSION% --product-version=%APP_VERSION% --copyright="CVAnalysis contributors""
set "DLL_CACHE_OPTION="
if /i "%CVANALYSIS_FORCE_DLL_CACHE%"=="1" set "DLL_CACHE_OPTION=--force-dll-dependency-cache-update"

if /i not "%BUILD_MODE%"=="onefile" (
    call :build_standalone
    if errorlevel 1 exit /b 1
)
if /i not "%BUILD_MODE%"=="standalone" (
    call :build_onefile
    if errorlevel 1 exit /b 1
)

echo.
echo ========================================
echo  BUILD FINISHED: v%APP_VERSION%
echo ========================================
echo [NOTE] Unsigned executables may still trigger Windows SmartScreen or
echo        antivirus heuristics.  Distribute the StandAlone folder when
echo        possible; sign the executable for wider distribution.
echo.
if /i "%BUILD_PAUSE%"=="1" pause
exit /b 0

:build_standalone
echo.
echo [INFO] Building StandAlone...
echo.
"%PYTHON_EXE%" -m nuitka start_gui.py ^
  --standalone ^
  %COMMON_OPTIONS% ^
  %DLL_CACHE_OPTION% ^
  --remove-output ^
  --output-dir="%STANDALONE_OUTPUT_DIR%" ^
  --output-filename="CVAnalysis_v%APP_VERSION%.exe"
if errorlevel 1 (
    echo.
    echo [ERROR] Nuitka StandAlone build failed.
    exit /b 1
)
if not exist "%STANDALONE_OUTPUT_DIR%\start_gui.dist\CVAnalysis_v%APP_VERSION%.exe" (
    echo.
    echo [ERROR] StandAlone executable was not produced. Check antivirus quarantine.
    exit /b 1
)
if not exist "%STANDALONE_OUTPUT_DIR%\start_gui.dist\ffi.dll" (
    echo.
    echo [ERROR] ffi.dll missing from StandAlone. Nuitka DLL dependency scan failed.
    exit /b 1
)
echo [SUCCESS] StandAlone: %STANDALONE_OUTPUT_DIR%\start_gui.dist\CVAnalysis_v%APP_VERSION%.exe
exit /b 0

:build_onefile
echo.
echo [INFO] Building OneFile...
echo.
"%PYTHON_EXE%" -m nuitka start_gui.py ^
  --onefile ^
  --onefile-no-compression ^
  --onefile-tempdir-spec="%ONEFILE_TEMPDIR_SPEC%" ^
  %COMMON_OPTIONS% ^
  %DLL_CACHE_OPTION% ^
  --remove-output ^
  --output-dir="%ONEFILE_OUTPUT_DIR%" ^
  --output-filename="CVAnalysis_v%APP_VERSION%.exe"
if errorlevel 1 (
    echo.
    echo [ERROR] Nuitka OneFile build failed.
    exit /b 1
)
if not exist "%ONEFILE_OUTPUT_DIR%\CVAnalysis_v%APP_VERSION%.exe" (
    echo.
    echo [ERROR] OneFile executable was not produced. Check antivirus quarantine.
    exit /b 1
)
echo [SUCCESS] OneFile: %ONEFILE_OUTPUT_DIR%\CVAnalysis_v%APP_VERSION%.exe
exit /b 0

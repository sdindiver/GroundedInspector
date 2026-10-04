@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "CONFIG=inspect.config"

REM --- First run: create inspect.config from the example and ask the user to fill it in ---
if not exist "%CONFIG%" (
  if exist "inspect.config.example" (
    copy /y "inspect.config.example" "%CONFIG%" >nul
    echo Created "%CONFIG%" from the example.
    echo Open it, set ANTHROPIC_API_KEY and IMAGES_FOLDER, then run start.bat again.
  ) else (
    echo ERROR: "%CONFIG%" not found and no inspect.config.example to copy.
  )
  pause
  exit /b 1
)

REM --- Load KEY=VALUE lines from the config (lines starting with # are ignored) ---
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%CONFIG%") do set "%%A=%%B"

if "%ANTHROPIC_API_KEY%"=="" (
  echo ERROR: ANTHROPIC_API_KEY is empty in %CONFIG%.
  pause
  exit /b 1
)
if "%ANTHROPIC_API_KEY%"=="sk-ant-REPLACE_ME" (
  echo ERROR: ANTHROPIC_API_KEY is still the placeholder. Put your real key in %CONFIG%.
  pause
  exit /b 1
)
if "%IMAGES_FOLDER%"=="" (
  echo ERROR: IMAGES_FOLDER is empty in %CONFIG%.
  pause
  exit /b 1
)
if not exist "%IMAGES_FOLDER%" (
  echo ERROR: IMAGES_FOLDER does not exist: "%IMAGES_FOLDER%"
  pause
  exit /b 1
)
if "%PART%"=="" set "PART=bracket"

echo.
echo === Installing dependencies ===
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install failed. Is Python installed and on PATH?
  pause
  exit /b 1
)

echo.
echo === Inspecting "%IMAGES_FOLDER%" as part "%PART%" ===
python -m grounded_inspector.inspect --part "%PART%" --folder "%IMAGES_FOLDER%"
if errorlevel 1 (
  echo Inspection failed. Check the error above.
  pause
  exit /b 1
)

echo.
echo === Done. Annotated images are in "%IMAGES_FOLDER%\annotated" ===
pause
endlocal

@echo off
setlocal
cd /d "%~dp0"

REM Grounding is configured in grounding/*.json. Runtime secrets/paths come from
REM environment variables; no inspect.config file is used.
if "%ANTHROPIC_API_KEY%"=="" (
  echo ERROR: ANTHROPIC_API_KEY is not set in the environment.
  echo Set it before running start.bat.
  pause
  exit /b 1
)
if "%IMAGES_FOLDER%"=="" (
  set /p "IMAGES_FOLDER=Enter the image folder path: "
)
if "%IMAGES_FOLDER%"=="" (
  echo ERROR: IMAGES_FOLDER is empty.
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

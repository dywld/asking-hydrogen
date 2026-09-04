@echo off
chcp 65001 >nul
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python 이 없습니다. 지금 여는 페이지에서 설치하세요.
  echo  설치 화면 맨 아래 "Add python.exe to PATH" 에 꼭 체크한 뒤, 이 파일을 다시 더블클릭.
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
python tools\start.py
echo.
pause

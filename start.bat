@echo off
REM ===========================================================
REM  Span Tech CRM - تشغيل نسخة التجربة على ويندوز
REM  دوس دبل كليك على الملف ده.
REM ===========================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
title Span Tech CRM

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Node.js مش متنصّب على الجهاز ده.
  echo.
  echo   نزّله من:  https://nodejs.org
  echo   اختار نسخة LTS ^(لازم تكون 22.5 أو أحدث^)، وبعد التنصيب
  echo   اقفل النافذة دي وافتح الملف تاني.
  echo.
  pause
  exit /b 1
)

for /f "tokens=1 delims=." %%v in ('node -p "process.versions.node"') do set MAJOR=%%v
for /f "tokens=2 delims=." %%v in ('node -p "process.versions.node"') do set MINOR=%%v
if %MAJOR% LSS 22 goto oldnode
if %MAJOR% EQU 22 if %MINOR% LSS 5 goto oldnode
goto ready

:oldnode
echo.
echo   إصدار Node القديم مش كفاية.
node -p "'   الموجود عندك: ' + process.versions.node"
echo   المطلوب: 22.5 أو أحدث.  نزّل من https://nodejs.org
echo.
pause
exit /b 1

:ready
call npm run demo
if errorlevel 1 (
  echo.
  echo   حصلت مشكلة في التجهيز. صوّر الشاشة دي وابعتها.
  pause
  exit /b 1
)

REM يفتح المتصفح بعد ثانيتين، لما السيرفر يكون قام
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8090"

echo   السيرفر شغال. اقفل النافذة دي عشان توقفه.
echo.
call npm start
pause

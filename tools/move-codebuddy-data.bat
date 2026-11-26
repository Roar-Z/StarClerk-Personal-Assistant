@echo off
chcp 65001 >nul
setlocal
title 把 CodeBuddy 对话数据搬到 D 盘

set "SRC=%LOCALAPPDATA%\CodeBuddyExtension\Data"
set "DST=D:\CodeBuddyData\Data"
set "OLD=%LOCALAPPDATA%\CodeBuddyExtension\Data.old"

echo ================================================
echo  把 CodeBuddy 对话数据从 C 盘搬到 D 盘
echo ================================================
echo.
echo  C: %SRC%
echo  D: %DST%
echo.

echo 正在等 CodeBuddy CN 完全退出（可以现在去关掉它）...
:wait
tasklist /FI "IMAGENAME eq CodeBuddy CN.exe" /NH 2>nul | find /I "CodeBuddy CN" >nul
if not errorlevel 1 (
  timeout /t 2 /nobreak >nul
  goto wait
)
echo CodeBuddy 已退出。
echo.

if exist "%OLD%" (
  echo [停] 备份目录 %OLD% 已经存在，先手动处理它再跑这个脚本。
  pause
  exit /b 1
)

if not exist "%DST%" mkdir "%DST%"
echo 再同步一次最新数据...
robocopy "%SRC%" "%DST%" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 (
  echo [停] 复制没成功，原目录一个字都没动。
  pause
  exit /b 1
)

echo 把 C 盘原目录改名成备份...
move "%SRC%" "%OLD%" >nul
if errorlevel 1 (
  echo [停] 原目录还被占用，打开任务管理器确认没有 CodeBuddy CN.exe 再试。
  pause
  exit /b 1
)

echo 建立目录联接...
mklink /J "%SRC%" "%DST%"
if errorlevel 1 (
  echo [停] 联接失败，正在回滚。
  move "%OLD%" "%SRC%" >nul
  pause
  exit /b 1
)

echo.
echo 完成了。以后对话数据实际写在 D:\CodeBuddyData\Data，
echo C 盘那个路径只是个入口，几乎不占空间。
echo.
echo 旧备份在：%OLD%
echo 用几天确认没问题后，手动删掉它就能再腾出约 2 GB。
pause

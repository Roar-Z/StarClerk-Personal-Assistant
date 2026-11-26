@echo off
chcp 65001 >nul
setlocal
title 把 CodeBuddy 对话数据从 D 盘放回 C 盘

set "LINK=%LOCALAPPDATA%\CodeBuddyExtension\Data"
set "DST=D:\CodeBuddyData\Data"

echo ================================================
echo  把 CodeBuddy 对话数据搬回 C 盘
echo ================================================
echo.
echo  D: %DST%
echo  C: %LINK%
echo.

echo 正在等 CodeBuddy CN 完全退出...
:wait
tasklist /FI "IMAGENAME eq CodeBuddy CN.exe" /NH 2>nul | find /I "CodeBuddy CN" >nul
if not errorlevel 1 (
  timeout /t 2 /nobreak >nul
  goto wait
)
echo CodeBuddy 已退出。
echo.

fsutil reparsepoint query "%LINK%" >nul 2>nul
if errorlevel 1 (
  echo [停] %LINK% 不是目录联接，可能已经搬回来了，不用再跑。
  pause
  exit /b 1
)

echo 删掉目录联接（只删入口，D 盘数据一个字都不动）...
rmdir "%LINK%"
if errorlevel 1 (
  echo [停] 入口删不掉，确认没有程序占着这个目录。
  pause
  exit /b 1
)

echo 把 D 盘的数据复制回 C 盘...
robocopy "%DST%" "%LINK%" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 (
  echo [停] 复制失败，但 D 盘数据还在，没丢。
  pause
  exit /b 1
)

echo.
echo 完成了。对话数据已经回到：
echo %LINK%
echo.
echo D 盘那份 %DST% 先留着，确认历史对话都在再手动删掉。
pause

@echo off
setlocal
cd /d "%~dp0"
title shifu - one-click start

echo ==============================================================
echo   shifu - AI Martial Arts Training Platform
echo ==============================================================
echo.

REM ================= prerequisites =================
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 20+
    pause
    exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    pause
    exit /b 1
)

REM ================= 1. business API  NestJS :3000 =================
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [SKIP] business API already running on :3000
    goto ai
)
echo [START] business API NestJS :3000 ...
if not exist "server\node_modules" (
    echo        installing node dependencies, please wait...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed
        pause
        exit /b 1
    )
)
if not exist "server\dist\main.js" (
    echo        building server...
    pushd server
    call npm run build
    if errorlevel 1 (
        popd
        echo [ERROR] server build failed
        pause
        exit /b 1
    )
    popd
)
if not exist "server\prisma\data\dev.db" (
    echo        initializing database...
    pushd server
    call npx prisma migrate deploy
    call npx prisma db seed
    popd
)
start "shifu-server" cmd /k "cd /d %~dp0server && node dist\main.js"
echo        started in a new window

:ai
REM ================= 2. AI service  FastAPI :8000 =================
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [SKIP] AI service already running on :8000
    goto web
)
echo [START] AI service FastAPI :8000 ...
if not exist "ai\.venv\Scripts\python.exe" (
    echo        creating python venv and installing deps, please wait...
    pushd ai
    python -m venv .venv
    .venv\Scripts\python -m pip install -q -r requirements.txt
    if errorlevel 1 (
        popd
        echo [ERROR] python deps install failed
        pause
        exit /b 1
    )
    popd
)
start "shifu-ai" cmd /k "cd /d %~dp0ai && .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo        started in a new window ^(pose model auto-downloads on first run^)

:web
REM ================= 3. frontend  Vite :5173 =================
netstat -ano | findstr ":5173" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [SKIP] frontend already running on :5173
    goto ready
)
echo [START] frontend Vite :5173 ...
if not exist "web\node_modules" (
    pushd web
    call npm install
    if errorlevel 1 (
        popd
        echo [ERROR] frontend deps install failed
        pause
        exit /b 1
    )
    popd
)
start "shifu-web" cmd /k "cd /d %~dp0web && npx vite --port 5173"
echo        started in a new window

:ready
REM ================= wait for frontend then open browser =================
echo.
echo [WAIT] waiting for frontend to be ready...
set /a tries=0
:waitloop
timeout /t 2 /nobreak >nul
curl -s -o nul http://localhost:5173 >nul 2>nul
if not errorlevel 1 goto open
set /a tries+=1
if %tries% lss 15 goto waitloop
echo [WARN] frontend not ready yet, open http://localhost:5173 later
goto done

:open
start "" http://localhost:5173
echo [DONE] browser opened at http://localhost:5173

:done
echo.
echo ==============================================================
echo   Each service runs in its own window. Close a window to
echo   stop that service.
echo   Default accounts: admin/admin123 (admin)  user1/123456 (user)
echo ==============================================================
pause

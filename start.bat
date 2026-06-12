@echo off
chcp 65001 >nul
echo ==========================================
echo   阿里系供应链直签服务商精英培训会 - 启动中...
echo ==========================================

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 创建虚拟环境
if not exist "venv" (
    echo 📦 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 安装依赖
echo 📦 安装依赖...
pip install -r requirements.txt -q

REM 创建上传目录
if not exist "uploads\videos" mkdir uploads\videos
if not exist "uploads\pdfs" mkdir uploads\pdfs
if not exist "uploads\covers" mkdir uploads\covers

REM 启动应用
echo.
echo 🚀 启动应用服务器...
echo.
python app.py

pause

@echo off
REM Streamlit 调试面板快速启动脚本

echo ========================================
echo   世界杯预测系统 - Streamlit 调试面板
echo ========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo [1/3] 检查依赖包...
pip show streamlit >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 Streamlit...
    pip install streamlit>=1.30.0 requests>=2.31.0 -q
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo [成功] 依赖安装完成
) else (
    echo [成功] Streamlit 已安装
)

echo.
echo [2/3] 检查 FastAPI 服务状态...
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [警告] FastAPI 服务未运行
    echo [提示] 请在新终端窗口中运行: uvicorn main:app --reload
    echo [提示] 按任意键继续启动 Streamlit（API 连接可能失败）
    pause >nul
) else (
    echo [成功] FastAPI 服务正在运行
)

echo.
echo [3/3] 启动 Streamlit 调试面板...
echo.
echo ========================================
echo   浏览器将自动打开 http://localhost:8501
echo   按 Ctrl+C 可停止服务
echo ========================================
echo.

streamlit run debug_dashboard.py

pause

@echo off
set PYTHONPATH=%~dp0
python -m streamlit run "%~dp0dashboard\app.py"

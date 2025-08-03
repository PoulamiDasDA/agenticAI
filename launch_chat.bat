@echo off
REM Earth at Night AI Chat Interface
REM Launch script for Windows

echo 🌍 Starting Earth at Night AI Chat Interface...

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate

REM Install requirements
echo 📋 Installing requirements...
pip install -r requirements_ui.txt

REM Check if .env file exists
if not exist ".env" (
    echo ⚠️  Warning: .env file not found!
    echo Please ensure your .env file contains all required Azure configuration.
    pause
    exit /b 1
)

REM Launch Streamlit app
echo 🚀 Launching chat interface...
echo 📱 The app will open in your browser at: http://localhost:8501
echo 🛑 Press Ctrl+C to stop the application

streamlit run chat_ui.py --server.port 8501 --server.address localhost

pause

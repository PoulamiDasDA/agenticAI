#!/bin/bash

# Earth at Night AI Chat Interface
# Launch script for the Streamlit web application

echo "🌍 Starting Earth at Night AI Chat Interface..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate  # For Linux/Mac
# venv\Scripts\activate  # For Windows (uncomment this line and comment above for Windows)

# Install requirements
echo "📋 Installing requirements..."
pip install -r requirements_ui.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "Please ensure your .env file contains all required Azure configuration."
    exit 1
fi

# Launch Streamlit app
echo "🚀 Launching chat interface..."
echo "📱 The app will open in your browser at: http://localhost:8501"
echo "🛑 Press Ctrl+C to stop the application"

streamlit run chat_ui.py --server.port 8501 --server.address localhost

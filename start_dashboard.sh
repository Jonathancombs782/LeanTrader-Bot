#!/bin/bash

# Start Trading Bot Dashboard
echo "🚀 Starting Trading Bot Dashboard..."

cd /home/$USER/trading-bot
source venv/bin/activate

# Start Streamlit dashboard
streamlit run dashboard_app.py --server.port 8501 --server.address 0.0.0.0
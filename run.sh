#!/bin/bash

# Ensure we are in the correct directory (where the script is located)
cd "$(dirname "$0")"

# Check if venv exists, if not, warn the user
if [ ! -d "venv" ]; then
    echo "Error: 'venv' directory not found."
    echo "Please run: python3 -m venv venv"
    exit 1
fi

# Activate the virtual environment
source venv/bin/activate

# Run the app
# --server.headless true: Don't try to open a browser on the server
# --server.address 0.0.0.0: Listen on all network interfaces (useful if you access this from another PC)
echo "Starting Stock Dashboard..."
streamlit run app.py --server.headless true --server.address 0.0.0.0
#if you use reverse proxy comment lie above, uncomment below and add path (/abc.de/stocks/ in this example)
#streamlit run app.py --server.headless true --server.address 0.0.0.0 --server.baseUrlPath /stocks

#!/usr/bin/env python3
"""
Start both the Flask API server and HTTP server for PDF Extractor
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Change to script directory
os.chdir(Path(__file__).parent)

print("""
╔════════════════════════════════════════════════════════════╗
║        PDF Schedule Extractor - Starting All Services      ║
╚════════════════════════════════════════════════════════════╝
""")

# Start Flask API server
print("Starting Flask API server on port 5000...")
flask_process = subprocess.Popen(
    [sys.executable, "space_api_server.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# Give Flask time to start
time.sleep(2)

# Start HTTP server
print("Starting HTTP server on port 8080...")
print("\n" + "="*60)
print("  Access the application at: http://localhost:8080")
print("="*60 + "\n")

try:
    subprocess.run([sys.executable, "serve.py"])
except KeyboardInterrupt:
    print("\nShutting down servers...")
    flask_process.terminate()
    print("Servers stopped.")
    sys.exit(0)
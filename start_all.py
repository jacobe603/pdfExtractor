#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

os.chdir(Path(__file__).parent)

print("Starting servers...")

# Use venv Python if available, otherwise use system Python
venv_python = Path(__file__).parent / "venv" / "bin" / "python"
python_exe = str(venv_python) if venv_python.exists() else sys.executable

flask_process = subprocess.Popen([python_exe, "space_api_server.py"])

http_process = subprocess.Popen([sys.executable, "-m", "http.server", "8080"])

print("Servers started.")
print("Access the application at: http://localhost:8080/index.html")

try:
    flask_process.wait()
    http_process.wait()
except KeyboardInterrupt:
    print("\nShutting down servers...")
    flask_process.terminate()
    http_process.terminate()
    print("Servers stopped.")
    sys.exit(0)

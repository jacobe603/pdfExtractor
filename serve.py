#!/usr/bin/env python3
"""
Simple HTTP server for PDF Extractor
Serves files locally to avoid CORS issues with file:// protocol
"""

import http.server
import socketserver
import os
import sys
from pathlib import Path

# Change to the script's directory
os.chdir(Path(__file__).parent)

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

# Configure MIME types
Handler.extensions_map.update({
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.css': 'text/css',
    '.html': 'text/html',
    '.pdf': 'application/pdf',
})

print(f"""
╔════════════════════════════════════════════════════════════╗
║           PDF Schedule Extractor - Local Server           ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Server starting on: http://localhost:{PORT}              ║
║                                                            ║
║  Open your browser to: http://localhost:{PORT}/index.html ║
║                                                            ║
║  Press Ctrl+C to stop the server                          ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""")

try:
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        httpd.serve_forever()
except KeyboardInterrupt:
    print("\n\nServer stopped.")
    sys.exit(0)
except OSError as e:
    if e.errno == 98:  # Port already in use
        print(f"\nError: Port {PORT} is already in use.")
        print("Try closing other applications or use a different port.")
    else:
        print(f"\nError starting server: {e}")
    sys.exit(1)
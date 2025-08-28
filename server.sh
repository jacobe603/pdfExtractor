#!/bin/bash

# PDF Extractor Server Management Script
# Manages both the Flask API server and HTTP frontend server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
API_PORT=5000
HTTP_PORT=8080
VENV_DIR="venv"
PID_DIR="/tmp/pdfextractor"
API_PID_FILE="$PID_DIR/api_server.pid"
HTTP_PID_FILE="$PID_DIR/http_server.pid"
API_LOG_FILE="$PID_DIR/api_server.log"
HTTP_LOG_FILE="$PID_DIR/http_server.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure PID directory exists
mkdir -p "$PID_DIR"

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process by PID file
kill_by_pidfile() {
    local pidfile=$1
    local name=$2
    
    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
            kill "$pid"
            sleep 2
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}Force stopping $name...${NC}"
                kill -9 "$pid"
            fi
        fi
        rm -f "$pidfile"
    fi
}

# Function to setup virtual environment
setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv "$VENV_DIR"
    fi
    
    echo -e "${YELLOW}Installing/updating dependencies...${NC}"
    source "$VENV_DIR/bin/activate"
    pip install -q --upgrade pip
    pip install -q flask flask-cors pymupdf pillow
}

# Function to start API server
start_api() {
    if [ -f "$API_PID_FILE" ]; then
        local pid=$(cat "$API_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}API server already running (PID: $pid)${NC}"
            return 0
        fi
    fi
    
    if check_port $API_PORT; then
        echo -e "${RED}Port $API_PORT is already in use!${NC}"
        echo "Attempting to find and stop the process..."
        lsof -ti:$API_PORT | xargs kill -9 2>/dev/null
        sleep 2
    fi
    
    echo -e "${YELLOW}Starting API server on port $API_PORT...${NC}"
    source "$VENV_DIR/bin/activate"
    nohup python space_api_server.py > "$API_LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$API_PID_FILE"
    
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}API server started successfully (PID: $pid)${NC}"
    else
        echo -e "${RED}Failed to start API server${NC}"
        rm -f "$API_PID_FILE"
        return 1
    fi
}

# Function to start HTTP server
start_http() {
    if [ -f "$HTTP_PID_FILE" ]; then
        local pid=$(cat "$HTTP_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}HTTP server already running (PID: $pid)${NC}"
            return 0
        fi
    fi
    
    if check_port $HTTP_PORT; then
        echo -e "${RED}Port $HTTP_PORT is already in use!${NC}"
        echo "Attempting to find and stop the process..."
        lsof -ti:$HTTP_PORT | xargs kill -9 2>/dev/null
        sleep 2
    fi
    
    echo -e "${YELLOW}Starting HTTP server on port $HTTP_PORT...${NC}"
    nohup python3 -m http.server $HTTP_PORT > "$HTTP_LOG_FILE" 2>&1 &
    local pid=$!
    echo $pid > "$HTTP_PID_FILE"
    
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}HTTP server started successfully (PID: $pid)${NC}"
    else
        echo -e "${RED}Failed to start HTTP server${NC}"
        rm -f "$HTTP_PID_FILE"
        return 1
    fi
}

# Function to stop servers
stop_servers() {
    echo -e "${YELLOW}Stopping servers...${NC}"
    
    # Stop API server
    kill_by_pidfile "$API_PID_FILE" "API server"
    
    # Stop HTTP server
    kill_by_pidfile "$HTTP_PID_FILE" "HTTP server"
    
    # Clean up any orphaned processes on the ports
    if check_port $API_PORT; then
        echo -e "${YELLOW}Cleaning up port $API_PORT...${NC}"
        lsof -ti:$API_PORT | xargs kill -9 2>/dev/null
    fi
    
    if check_port $HTTP_PORT; then
        echo -e "${YELLOW}Cleaning up port $HTTP_PORT...${NC}"
        lsof -ti:$HTTP_PORT | xargs kill -9 2>/dev/null
    fi
    
    echo -e "${GREEN}All servers stopped${NC}"
}

# Function to check server status
status() {
    echo -e "${YELLOW}=== Server Status ===${NC}"
    
    # Check API server
    if [ -f "$API_PID_FILE" ]; then
        local pid=$(cat "$API_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}API server: Running (PID: $pid, Port: $API_PORT)${NC}"
        else
            echo -e "${RED}API server: PID file exists but process not running${NC}"
        fi
    else
        if check_port $API_PORT; then
            echo -e "${YELLOW}API server: Running on port $API_PORT (not managed by this script)${NC}"
        else
            echo -e "${RED}API server: Not running${NC}"
        fi
    fi
    
    # Check HTTP server
    if [ -f "$HTTP_PID_FILE" ]; then
        local pid=$(cat "$HTTP_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}HTTP server: Running (PID: $pid, Port: $HTTP_PORT)${NC}"
        else
            echo -e "${RED}HTTP server: PID file exists but process not running${NC}"
        fi
    else
        if check_port $HTTP_PORT; then
            echo -e "${YELLOW}HTTP server: Running on port $HTTP_PORT (not managed by this script)${NC}"
        else
            echo -e "${RED}HTTP server: Not running${NC}"
        fi
    fi
    
    echo ""
    echo "URLs:"
    echo "  - Main application: http://localhost:$HTTP_PORT/index.html"
    echo "  - Equipment browser: http://localhost:$HTTP_PORT/equipment-browser.html"
    echo "  - API endpoint: http://localhost:$API_PORT/api/health"
    echo ""
    echo "Log files:"
    echo "  - API server: $API_LOG_FILE"
    echo "  - HTTP server: $HTTP_LOG_FILE"
}

# Function to show logs
logs() {
    local server=$1
    
    case $server in
        api)
            if [ -f "$API_LOG_FILE" ]; then
                echo -e "${YELLOW}=== API Server Logs ===${NC}"
                tail -n 50 "$API_LOG_FILE"
            else
                echo -e "${RED}No API server logs found${NC}"
            fi
            ;;
        http)
            if [ -f "$HTTP_LOG_FILE" ]; then
                echo -e "${YELLOW}=== HTTP Server Logs ===${NC}"
                tail -n 50 "$HTTP_LOG_FILE"
            else
                echo -e "${RED}No HTTP server logs found${NC}"
            fi
            ;;
        *)
            echo -e "${YELLOW}=== Recent Logs ===${NC}"
            if [ -f "$API_LOG_FILE" ]; then
                echo -e "${YELLOW}API Server:${NC}"
                tail -n 20 "$API_LOG_FILE"
                echo ""
            fi
            if [ -f "$HTTP_LOG_FILE" ]; then
                echo -e "${YELLOW}HTTP Server:${NC}"
                tail -n 20 "$HTTP_LOG_FILE"
            fi
            ;;
    esac
}

# Main command handling
case "$1" in
    start)
        echo -e "${GREEN}=== Starting PDF Extractor Servers ===${NC}"
        setup_venv
        start_api
        start_http
        echo ""
        status
        ;;
    
    stop)
        echo -e "${RED}=== Stopping PDF Extractor Servers ===${NC}"
        stop_servers
        ;;
    
    restart)
        echo -e "${YELLOW}=== Restarting PDF Extractor Servers ===${NC}"
        stop_servers
        sleep 2
        setup_venv
        start_api
        start_http
        echo ""
        status
        ;;
    
    status)
        status
        ;;
    
    logs)
        logs "$2"
        ;;
    
    clean)
        echo -e "${RED}=== Cleaning up ===${NC}"
        stop_servers
        echo -e "${YELLOW}Removing PID files and logs...${NC}"
        rm -f "$API_PID_FILE" "$HTTP_PID_FILE" "$API_LOG_FILE" "$HTTP_LOG_FILE"
        echo -e "${GREEN}Cleanup complete${NC}"
        ;;
    
    apikey)
        echo -e "${YELLOW}=== Gemini API Key Management ===${NC}"
        if [ "$2" == "set" ]; then
            if [ -z "$3" ]; then
                echo -e "${RED}Error: Please provide an API key${NC}"
                echo "Usage: $0 apikey set YOUR_API_KEY"
                exit 1
            fi
            echo "$3" > "$HOME/.gemini_api_key"
            chmod 600 "$HOME/.gemini_api_key"
            echo -e "${GREEN}✓ API key saved successfully${NC}"
        elif [ "$2" == "check" ]; then
            if [ -f "$HOME/.gemini_api_key" ]; then
                KEY=$(cat "$HOME/.gemini_api_key" | grep -v '^#' | head -n 1)
                if [ "$KEY" != "YOUR_API_KEY_HERE" ] && [ -n "$KEY" ]; then
                    echo -e "${GREEN}✓ API key is configured${NC}"
                    echo "Key starts with: ${KEY:0:10}..."
                else
                    echo -e "${YELLOW}⚠ API key file exists but is not configured${NC}"
                fi
            else
                echo -e "${RED}✗ No API key file found${NC}"
            fi
        else
            echo "Usage: $0 apikey {set|check}"
            echo "  set KEY  - Set the Gemini API key"
            echo "  check    - Check if API key is configured"
        fi
        ;;
    
    *)
        echo "PDF Extractor Server Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|clean|apikey}"
        echo ""
        echo "Commands:"
        echo "  start    - Start both API and HTTP servers"
        echo "  stop     - Stop all servers"
        echo "  restart  - Restart all servers"
        echo "  status   - Show server status"
        echo "  logs [api|http] - Show server logs (last 50 lines)"
        echo "  clean    - Stop servers and clean up all files"
        echo "  apikey {set|check} - Manage Gemini API key"
        echo ""
        echo "Configuration:"
        echo "  API Port: $API_PORT"
        echo "  HTTP Port: $HTTP_PORT"
        echo "  PID Directory: $PID_DIR"
        exit 1
        ;;
esac

exit 0
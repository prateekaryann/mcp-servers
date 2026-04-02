#!/bin/bash
# Start GitHub MCP server with ngrok tunnel for personal remote access
# Usage: ./tunnel.sh [--port 8080] [--read-only]

set -e

PORT=${MCP_PORT:-8080}
READ_ONLY_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --port) PORT="$2"; shift 2;;
        --read-only) READ_ONLY_FLAG="READ_ONLY=true"; shift;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

# Check prerequisites
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok not found. Install from: https://ngrok.com/download"
    echo "   Then run: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
fi

if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) not found. Install from: https://cli.github.com/"
    exit 1
fi

# Generate API key if not set
if [ -z "$MCP_API_KEY" ]; then
    export MCP_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "🔑 Generated MCP_API_KEY: $MCP_API_KEY"
    echo "   Save this — you'll need it to connect from Claude."
fi

echo ""
echo "🚀 Starting GitHub MCP Server on port $PORT..."
echo "   Mode: $([ -n "$READ_ONLY_FLAG" ] && echo 'READ-ONLY' || echo 'FULL ACCESS')"
echo ""

# Start server in background
export MCP_TRANSPORT=sse
export MCP_PORT=$PORT
$READ_ONLY_FLAG python server.py &
SERVER_PID=$!

# Give server a moment to start
sleep 2

# Start ngrok with basic auth
echo "🌐 Starting ngrok tunnel..."
ngrok http $PORT --log=stdout &
NGROK_PID=$!

sleep 3

# Get the public URL
NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels | python -c "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || echo "Check http://127.0.0.1:4040")

echo ""
echo "============================================"
echo "✅ MCP Server is running!"
echo ""
echo "   Local:  http://localhost:$PORT/sse"
echo "   Tunnel: $NGROK_URL/sse"
echo ""
echo "   API Key: $MCP_API_KEY"
echo ""
echo "   Add to Claude.ai MCP settings:"
echo "   URL: $NGROK_URL/sse"
echo "   Header: Authorization: Bearer $MCP_API_KEY"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop"

# Cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    kill $SERVER_PID 2>/dev/null
    kill $NGROK_PID 2>/dev/null
    echo "Done."
}
trap cleanup EXIT

# Wait
wait

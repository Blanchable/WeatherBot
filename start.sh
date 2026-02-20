#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════╗
# ║  Kalshi Market Making Bot - One-Click Launcher          ║
# ║  Double-click or run: ./start.sh                        ║
# ║  Automatically installs everything on first run.        ║
# ╚══════════════════════════════════════════════════════════╝
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${BLUE}${BOLD}  ┌──────────────────────────────────────────┐${NC}"
echo -e "${BLUE}${BOLD}  │   Kalshi Market Making Bot - Launcher    │${NC}"
echo -e "${BLUE}${BOLD}  └──────────────────────────────────────────┘${NC}"
echo ""

# ── Find Python ──────────────────────────────────────────
echo -e "${BOLD}[1/4]${NC} Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major="${ver%%.*}"
        minor="${ver##*.}"
        if [ "$major" -ge 3 ] 2>/dev/null && [ "$minor" -ge 10 ] 2>/dev/null; then
            PYTHON="$cmd"
            echo -e "  ${GREEN}Found $cmd ($($cmd --version 2>&1))${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}Python 3.10+ is required but not found.${NC}"
    echo ""
    echo "  Install Python:"
    echo "    Ubuntu/Debian:  sudo apt install python3"
    echo "    Fedora:         sudo dnf install python3"
    echo "    macOS:          brew install python3"
    echo "    Or download:    https://www.python.org/downloads/"
    echo ""
    read -rp "  Press Enter to exit..." _
    exit 1
fi

# ── Check Tkinter ────────────────────────────────────────
if ! $PYTHON -c "import tkinter" 2>/dev/null; then
    echo -e "  ${YELLOW}Installing Tkinter...${NC}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq python3-tk 2>/dev/null
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-tkinter 2>/dev/null
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm tk 2>/dev/null
    elif command -v brew &>/dev/null; then
        brew install python-tk 2>/dev/null
    fi
    if ! $PYTHON -c "import tkinter" 2>/dev/null; then
        echo -e "  ${RED}Could not install Tkinter. Install manually:${NC}"
        echo "    Ubuntu/Debian: sudo apt install python3-tk"
        echo "    Fedora:        sudo dnf install python3-tkinter"
        echo "    macOS:         brew install python-tk"
        read -rp "  Press Enter to exit..." _
        exit 1
    fi
    echo -e "  ${GREEN}Tkinter installed${NC}"
fi

# ── Create venv if needed ────────────────────────────────
echo -e "${BOLD}[2/4]${NC} Setting up environment..."
VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    if ! $PYTHON -m venv "$VENV" --system-site-packages 2>/dev/null; then
        echo -e "  ${YELLOW}Installing python3-venv...${NC}"
        PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq "python${PY_VER}-venv" 2>/dev/null
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y "python${PY_VER}-venv" 2>/dev/null || true
        fi
        $PYTHON -m venv "$VENV" --system-site-packages
    fi
    echo -e "  ${GREEN}Created virtual environment${NC}"
else
    echo -e "  ${GREEN}Environment exists${NC}"
fi

source "$VENV/bin/activate"

# ── Install deps if needed ───────────────────────────────
echo -e "${BOLD}[3/4]${NC} Checking dependencies..."
if ! python -c "import requests; import websocket; import numpy" 2>/dev/null; then
    echo -e "  ${YELLOW}Installing dependencies...${NC}"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo -e "  ${GREEN}Dependencies installed${NC}"
else
    echo -e "  ${GREEN}Dependencies OK${NC}"
fi

# ── Verify ───────────────────────────────────────────────
echo -e "${BOLD}[4/4]${NC} Verifying..."
python -c "import requests; import websocket; import numpy; import tkinter; print('  All good')"

# ── Launch ───────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  ┌──────────────────────────────────────────┐${NC}"
echo -e "${GREEN}${BOLD}  │          Launching Bot...                │${NC}"
echo -e "${GREEN}${BOLD}  └──────────────────────────────────────────┘${NC}"
echo ""

python -m kalshi_bot.main "$@"

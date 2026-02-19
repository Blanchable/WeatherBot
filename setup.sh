#!/usr/bin/env bash
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║     Kalshi Market Making Bot - Installer     ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Check Python ──────────────────────────────────────────
echo -e "${BOLD}[1/5] Checking Python installation...${NC}"
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            echo -e "  ${GREEN}Found $cmd ($("$cmd" --version))${NC}"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}Python 3.10+ is required but not found.${NC}"
    echo -e "  Install Python from https://www.python.org/downloads/"
    exit 1
fi

# ── Check Tkinter ─────────────────────────────────────────
echo -e "${BOLD}[2/5] Checking Tkinter availability...${NC}"
if $PYTHON -c "import tkinter" 2>/dev/null; then
    echo -e "  ${GREEN}Tkinter is available${NC}"
else
    echo -e "  ${YELLOW}Tkinter not found. Attempting to install...${NC}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq python3-tk
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-tkinter
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm tk
    elif command -v brew &>/dev/null; then
        brew install python-tk
    else
        echo -e "  ${RED}Could not install Tkinter automatically.${NC}"
        echo -e "  Please install it manually for your OS."
        echo -e "  Ubuntu/Debian: sudo apt install python3-tk"
        echo -e "  Fedora: sudo dnf install python3-tkinter"
        echo -e "  macOS: brew install python-tk"
        exit 1
    fi

    if $PYTHON -c "import tkinter" 2>/dev/null; then
        echo -e "  ${GREEN}Tkinter installed successfully${NC}"
    else
        echo -e "  ${RED}Tkinter installation failed. Please install manually.${NC}"
        exit 1
    fi
fi

# ── Create Virtual Environment ────────────────────────────
echo -e "${BOLD}[3/5] Setting up virtual environment...${NC}"
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR" --system-site-packages
    echo -e "  ${GREEN}Created virtual environment at .venv/${NC}"
else
    echo -e "  ${GREEN}Virtual environment already exists${NC}"
fi

source "$VENV_DIR/bin/activate"

# ── Install Dependencies ──────────────────────────────────
echo -e "${BOLD}[4/5] Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo -e "  ${GREEN}Dependencies installed${NC}"

# ── Verify Installation ───────────────────────────────────
echo -e "${BOLD}[5/5] Verifying installation...${NC}"
$PYTHON -c "
import requests
import websocket
import numpy
import tkinter
print('  All modules verified')
"
echo -e "  ${GREEN}Installation verified successfully${NC}"

# ── Create Launcher Scripts ───────────────────────────────
cat > "$SCRIPT_DIR/run.sh" << 'LAUNCHER'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
cd "$SCRIPT_DIR"
python -m kalshi_bot.main "$@"
LAUNCHER
chmod +x "$SCRIPT_DIR/run.sh"

cat > "$SCRIPT_DIR/run_headless.sh" << 'LAUNCHER'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
cd "$SCRIPT_DIR"
python -m kalshi_bot.main --headless "$@"
LAUNCHER
chmod +x "$SCRIPT_DIR/run_headless.sh"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║         Installation Complete!                ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
echo -e "    ${BLUE}./run.sh${NC}           Launch with GUI (runs setup wizard on first run)"
echo -e "    ${BLUE}./run.sh --setup${NC}   Re-run the setup wizard"
echo -e "    ${BLUE}./run_headless.sh${NC}  Run without GUI"
echo ""
echo -e "  ${BOLD}Config location:${NC} ~/.kalshi_bot/"
echo ""

# Ask to run setup wizard
echo -e "${YELLOW}Would you like to run the setup wizard now? (y/n)${NC}"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    $PYTHON -m kalshi_bot.main --setup
fi

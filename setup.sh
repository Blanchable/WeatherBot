#!/usr/bin/env bash
#
# Kalshi Weather Bot — Setup Wizard Launcher
# Double-click this file (or run: bash setup.sh) to start the setup wizard.
#

set -e

echo ""
echo "  ============================================"
echo "   Kalshi Weather Bot - Setup Wizard"
echo "  ============================================"
echo ""

# Resolve the directory this script lives in (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Find a suitable Python 3.11+ interpreter
PYTHON_CMD=""

for candidate in python3 python python3.13 python3.12 python3.11; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            PYTHON_CMD="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "  [ERROR] Python 3.11+ not found."
    echo ""
    echo "  Install it with your package manager:"
    echo "    macOS:  brew install python@3.12"
    echo "    Ubuntu: sudo apt install python3.12 python3.12-venv"
    echo "    Fedora: sudo dnf install python3.12"
    echo ""
    echo "  Or download from https://www.python.org/downloads/"
    echo ""
    read -rp "  Press Enter to exit..."
    exit 1
fi

echo "  Using: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"
echo ""

# Ensure pip is available
if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
    echo "  Installing pip..."
    "$PYTHON_CMD" -m ensurepip --upgrade 2>/dev/null || true
fi

# Launch the setup wizard — it auto-installs deps on first run
"$PYTHON_CMD" "$SCRIPT_DIR/src/ui/setup_wizard.py"

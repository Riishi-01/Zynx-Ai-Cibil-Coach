#!/bin/bash
# CIBIL Credit Coach — Quick Test Script
# Run: bash QUICK_TEST.sh

set -e

echo "=========================================================================="
echo "CIBIL Credit Coach — Quick Test Setup"
echo "=========================================================================="
echo

# Step 1: Check Python
echo "[1/5] Checking Python..."
python3 --version
echo

# Step 2: Create venv
echo "[2/5] Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
source .venv/bin/activate
echo

# Step 3: Install deps
echo "[3/5] Installing dependencies..."
pip install --quiet -r requirements.txt
echo "✓ Dependencies installed"
echo

# Step 4: Test mock pipeline
echo "[4/5] Testing mock pipeline (no LLM calls)..."
python3 scripts/end_to_end_test.py 2>&1 | tail -15
echo

# Step 5: Instructions for real test
echo "[5/5] Ready for real LLM test!"
echo
echo "=========================================================================="
echo "To run with REAL OpenAI:"
echo "=========================================================================="
echo
echo "1. Get your OpenAI API key from https://platform.openai.com/api-keys"
echo
echo "2. Create .env file:"
echo "   cp .env.example .env"
echo "   nano .env  # Paste your API key"
echo
echo "3. Run the real test:"
echo "   export OPENAI_API_KEY='sk-...'"
echo "   python3 scripts/real_llm_test.py ABCPS1234A 75000"
echo
echo "=========================================================================="
echo "✓ Setup complete! Next: add your API key and run the real test."
echo "=========================================================================="

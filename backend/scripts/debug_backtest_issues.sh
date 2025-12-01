#!/bin/bash
# Debug Script for Backtest Issues
# Tests speed multiplier and quality calculation

echo "=============================================="
echo "Backtest Debug Session"
echo "=============================================="
echo ""
echo "This will:"
echo "1. Start the system"
echo "2. Watch for debug messages with emojis"
echo "3. Show quality and speed-related logs"
echo ""
echo "Look for these debug indicators:"
echo "  🔍 - Quality manager availability check"
echo "  📊 - Quality notification sent"
echo "  ❌ - Quality manager NOT available"
echo "  📬 - Quality notification received"
echo "  🔄 - Quality thread processing"
echo "  ✅ - Quality calculated successfully"
echo "  💾 - Quality saved to session data"
echo "  ⏱️  - Speed multiplier and delay info"
echo ""
echo "=============================================="
echo ""

# Check if in backend directory
if [ ! -f "start_cli.sh" ]; then
    echo "ERROR: Must run from backend directory"
    exit 1
fi

# Clean old logs
rm -f logs/*.log 2>/dev/null

echo "Starting CLI..."
echo "After system starts, type: data session"
echo ""
echo "Press Ctrl+C to stop when done"
echo ""

./start_cli.sh

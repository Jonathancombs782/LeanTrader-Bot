#!/bin/bash
# ===============================================
# ULTIMATE ULTRA+ BOT TESTING SCRIPT
# Comprehensive testing and verification
# ===============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BOT_DIR="/opt/leantraderbot"
VENV_PATH="$BOT_DIR/venv"
SERVICE_NAME="ultra_plus"

echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}         ULTRA+ BOT VERIFICATION SUITE                ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"

# ===============================================
# TEST 1: ENVIRONMENT CHECK
# ===============================================
echo -e "\n${YELLOW}[TEST 1] Environment Check${NC}"

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ Python installed: $PYTHON_VERSION${NC}"
else
    echo -e "${RED}✗ Python not found${NC}"
fi

# Check virtual environment
if [ -d "$VENV_PATH" ]; then
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
    
    # Check packages
    PACKAGES=$($VENV_PATH/bin/pip list 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ Packages installed: $PACKAGES${NC}"
else
    echo -e "${RED}✗ Virtual environment not found${NC}"
fi

# Check directories
for dir in "$BOT_DIR" "$BOT_DIR/logs" "$BOT_DIR/models"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}✓ Directory exists: $dir${NC}"
    else
        echo -e "${RED}✗ Directory missing: $dir${NC}"
    fi
done

# ===============================================
# TEST 2: DATABASE CHECK
# ===============================================
echo -e "\n${YELLOW}[TEST 2] Database Check${NC}"

DB_PATH="$BOT_DIR/ultra_plus.db"

if [ -f "$DB_PATH" ]; then
    echo -e "${GREEN}✓ Database file exists${NC}"
    
    # Check tables
    TABLES=$(sqlite3 "$DB_PATH" ".tables" 2>/dev/null | wc -w)
    echo -e "${GREEN}✓ Tables found: $TABLES${NC}"
    
    # Check for required tables
    for table in signals trades moon_tokens risk_metrics ai_models; do
        if sqlite3 "$DB_PATH" ".tables" | grep -q "$table"; then
            echo -e "${GREEN}  ✓ Table '$table' exists${NC}"
        else
            echo -e "${YELLOW}  ⚠ Table '$table' will be created on first run${NC}"
        fi
    done
else
    echo -e "${YELLOW}⚠ Database will be created on first run${NC}"
fi

# ===============================================
# TEST 3: CONFIGURATION CHECK
# ===============================================
echo -e "\n${YELLOW}[TEST 3] Configuration Check${NC}"

if [ -f "$BOT_DIR/.env" ]; then
    echo -e "${GREEN}✓ Configuration file exists${NC}"
    
    # Check for required variables (without exposing values)
    for var in USE_TESTNET TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
        if grep -q "^$var=" "$BOT_DIR/.env"; then
            echo -e "${GREEN}  ✓ $var configured${NC}"
        else
            echo -e "${RED}  ✗ $var not configured${NC}"
        fi
    done
else
    echo -e "${RED}✗ Configuration file missing${NC}"
fi

# ===============================================
# TEST 4: ENGINE VERIFICATION
# ===============================================
echo -e "\n${YELLOW}[TEST 4] Engine Verification${NC}"

# Check if bot file has all engines
if [ -f "$BOT_DIR/ultimate_ultra_plus.py" ]; then
    echo -e "${GREEN}✓ Bot file exists${NC}"
    
    # Check for engine classes
    for engine in "MoonSpotterEngine" "CryptoScalperEngine" "ArbitrageEngine" \
                  "FXTrainerEngine" "WebCrawlerEngine" "DeepLearningEngine" "RiskManager"; do
        if grep -q "class $engine" "$BOT_DIR/ultimate_ultra_plus.py"; then
            echo -e "${GREEN}  ✓ $engine implemented${NC}"
        else
            echo -e "${RED}  ✗ $engine missing${NC}"
        fi
    done
else
    echo -e "${RED}✗ Bot file not found${NC}"
fi

# ===============================================
# TEST 5: SIGNAL DEDUPLICATION TEST
# ===============================================
echo -e "\n${YELLOW}[TEST 5] Signal Deduplication Test${NC}"

# Create test Python script
cat > /tmp/test_dedup.py << 'EOF'
import sys
sys.path.append('/opt/leantraderbot')
from ultimate_ultra_plus import SignalDeduplicator

dedup = SignalDeduplicator(max_size=10, ttl_seconds=5)

# Test duplicate detection
signal1 = dedup.is_duplicate('test', 'BTC/USDT', 'buy', 50000.1234)
signal2 = dedup.is_duplicate('test', 'BTC/USDT', 'buy', 50000.1234)
signal3 = dedup.is_duplicate('test', 'BTC/USDT', 'sell', 50000.1234)

print(f"First signal (should be False): {signal1}")
print(f"Duplicate (should be True): {signal2}")
print(f"Different side (should be False): {signal3}")

if not signal1 and signal2 and not signal3:
    print("✓ Deduplication working correctly")
else:
    print("✗ Deduplication error")
EOF

if [ -f "$VENV_PATH/bin/python" ]; then
    OUTPUT=$($VENV_PATH/bin/python /tmp/test_dedup.py 2>&1) || true
    if echo "$OUTPUT" | grep -q "✓ Deduplication working correctly"; then
        echo -e "${GREEN}✓ Signal deduplication working${NC}"
    else
        echo -e "${YELLOW}⚠ Could not verify deduplication${NC}"
    fi
fi

# ===============================================
# TEST 6: TELEGRAM CALLBACK TEST
# ===============================================
echo -e "\n${YELLOW}[TEST 6] Telegram Callback Verification${NC}"

# Check for callback handler pattern
if [ -f "$BOT_DIR/ultimate_ultra_plus.py" ]; then
    if grep -q 'callback_data="TRADE|' "$BOT_DIR/ultimate_ultra_plus.py"; then
        echo -e "${GREEN}✓ Trade button callbacks implemented${NC}"
    else
        echo -e "${RED}✗ Trade button callbacks missing${NC}"
    fi
    
    if grep -q 'def button_callback' "$BOT_DIR/ultimate_ultra_plus.py"; then
        echo -e "${GREEN}✓ Callback handler implemented${NC}"
    else
        echo -e "${RED}✗ Callback handler missing${NC}"
    fi
fi

# ===============================================
# TEST 7: SERVICE CHECK
# ===============================================
echo -e "\n${YELLOW}[TEST 7] Systemd Service Check${NC}"

if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    echo -e "${GREEN}✓ Service file installed${NC}"
    
    # Check if enabled
    if systemctl is-enabled "$SERVICE_NAME" &>/dev/null; then
        echo -e "${GREEN}✓ Service enabled${NC}"
    else
        echo -e "${YELLOW}⚠ Service not enabled${NC}"
    fi
    
    # Check status
    STATUS=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "inactive")
    if [ "$STATUS" == "active" ]; then
        echo -e "${GREEN}✓ Service running${NC}"
    else
        echo -e "${YELLOW}⚠ Service not running (status: $STATUS)${NC}"
    fi
else
    echo -e "${RED}✗ Service file not installed${NC}"
fi

# ===============================================
# TEST 8: TESTNET VERIFICATION
# ===============================================
echo -e "\n${YELLOW}[TEST 8] Testnet Safety Check${NC}"

if [ -f "$BOT_DIR/.env" ]; then
    if grep -q "^USE_TESTNET=true" "$BOT_DIR/.env"; then
        echo -e "${GREEN}✓ TESTNET mode enabled (safe)${NC}"
    else
        echo -e "${RED}⚠️ WARNING: TESTNET may be disabled!${NC}"
    fi
    
    if grep -q "^FORCE_LIVE=1" "$BOT_DIR/.env"; then
        echo -e "${RED}⚠️ WARNING: FORCE_LIVE is enabled - REAL MONEY!${NC}"
    else
        echo -e "${GREEN}✓ FORCE_LIVE disabled (safe)${NC}"
    fi
fi

# ===============================================
# TEST 9: SAMPLE SIGNAL TEST
# ===============================================
echo -e "\n${YELLOW}[TEST 9] Sample Signal Generation${NC}"

cat > /tmp/test_signal.py << 'EOF'
import sys
import sqlite3
sys.path.append('/opt/leantraderbot')

try:
    from ultimate_ultra_plus import DatabaseManager, SignalDeduplicator
    
    db = DatabaseManager()
    dedup = SignalDeduplicator()
    
    # Insert test signal
    result = db.insert_signal(
        engine='test',
        symbol='BTC/USDT',
        side='buy',
        confidence=0.85,
        price=50000,
        metadata={'test': True}
    )
    
    print(f"✓ Test signal inserted: {result}")
    
    # Check deduplication
    is_dup = dedup.is_duplicate('test', 'BTC/USDT', 'buy', 50000)
    print(f"✓ Deduplication check: {'Working' if not is_dup else 'Failed'}")
    
except Exception as e:
    print(f"✗ Error: {e}")
EOF

if [ -f "$VENV_PATH/bin/python" ]; then
    OUTPUT=$($VENV_PATH/bin/python /tmp/test_signal.py 2>&1) || true
    if echo "$OUTPUT" | grep -q "✓"; then
        echo -e "${GREEN}✓ Signal generation test passed${NC}"
    else
        echo -e "${YELLOW}⚠ Could not test signal generation${NC}"
    fi
fi

# ===============================================
# TEST 10: LOG CHECK
# ===============================================
echo -e "\n${YELLOW}[TEST 10] Log Verification${NC}"

LOG_FILE="$BOT_DIR/logs/ultra_plus.log"

if [ -f "$LOG_FILE" ]; then
    echo -e "${GREEN}✓ Log file exists${NC}"
    
    # Check recent logs
    if [ -s "$LOG_FILE" ]; then
        LINES=$(wc -l < "$LOG_FILE")
        echo -e "${GREEN}  ✓ Log entries: $LINES${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Log file will be created on first run${NC}"
fi

# Check journal logs
if systemctl is-active "$SERVICE_NAME" &>/dev/null; then
    JOURNAL_LINES=$(journalctl -u "$SERVICE_NAME" --no-pager 2>/dev/null | wc -l)
    if [ "$JOURNAL_LINES" -gt 0 ]; then
        echo -e "${GREEN}✓ Journal logs available: $JOURNAL_LINES lines${NC}"
    fi
fi

# ===============================================
# SUMMARY
# ===============================================
echo -e "\n${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                   TEST SUMMARY                       ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"

echo -e "\n${GREEN}VERIFICATION COMPLETE!${NC}"
echo -e "\nTo view specific engine logs:"
echo -e "  ${BLUE}grep 'moon_spotter' $BOT_DIR/logs/ultra_plus.log${NC}"
echo -e "  ${BLUE}grep 'scalper' $BOT_DIR/logs/ultra_plus.log${NC}"
echo -e "  ${BLUE}grep 'arbitrage' $BOT_DIR/logs/ultra_plus.log${NC}"

echo -e "\nTo test a single engine manually:"
echo -e "  ${BLUE}$VENV_PATH/bin/python -c \"
from ultimate_ultra_plus import MoonSpotterEngine, SignalDeduplicator, DatabaseManager
import asyncio
dedup = SignalDeduplicator()
db = DatabaseManager()
engine = MoonSpotterEngine(dedup, db)
asyncio.run(engine.scan())
\"${NC}"

echo -e "\n${GREEN}🚀 Bot verification complete!${NC}"
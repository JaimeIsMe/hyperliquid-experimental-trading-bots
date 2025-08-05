# 🚀 Hyperliquid Trading Bots

A collection of professional-grade automated trading bots for the Hyperliquid DEX, featuring advanced order management, grouped TP/SL orders, and innovative trading strategies.

## 🤖 Available Bots

### 1. **Ultimate Scalping Bot** (`ultimate_scalping_bot.py`)
- **Strategy**: Price monitoring scalping with instant TP/SL placement
- **Features**: 
  - Grouped orders with `normalTpsl` for UI-visible TP/SL
  - Price monitoring for instant execution
  - Percentage-based TP/SL that scales with asset price
  - 20x leverage support

### 2. **Order Book Hunter** (`order_book_hunter.py`)
- **Strategy**: Order book imbalance detection + volume spike confirmation
- **Features**:
  - Real-time L2 order book analysis
  - Bid/ask imbalance ratio detection
  - Volume spike confirmation
  - Fast entry/exit with grouped TP/SL

### 3. **Experimental Color Trader** (`experimental_color_trader.py`)
- **Strategy**: Screen color detection from visual indicators
- **Features**:
  - Screen region capture and color analysis
  - K-means clustering for dominant color detection
  - Position flipping based on color signals
  - 40x leverage with automatic position management

## 📋 Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Setup
Copy the example environment file and configure it:
```bash
cp .env.example .env
```

Then edit `.env` and fill in your actual values:
- `HYPERLIQUID_PRIVATE_KEY`: Your Hyperliquid private key (64-character hex string)
- `WALLET_ADDRESS`: Your wallet address (0x...)
- `LIVE_TRADING`: Set to `true` when ready for real trading (starts as `false`)

**⚠️ IMPORTANT**: Never share your `.env` file or commit it to version control!

### 3. Run a Bot

#### Option A: Command Line (Traditional)
```bash
# Ultimate Scalping Bot
python3 ultimate_scalping_bot.py

# Order Book Hunter
python3 order_book_hunter.py

# Experimental Color Trader
python3 experimental_color_trader.py
```

#### Option B: Web Interface (Recommended for Color Trader) 🆕
```bash
# Launch the web dashboard for Color Trader
python3 start_web_interface.py
```

The web interface provides:
- 🎨 **Real-time color detection visualization**
- 📊 **Live trading dashboard with position status**
- 🖱️ **Interactive screen region calibration**
- 📈 **Trade history and P&L tracking**
- 🎛️ **Easy bot controls (start/stop/settings)**
- 📱 **Modern responsive web UI**

Access the dashboard at: `http://localhost:8000`

## 📚 Documentation

See `HYPERLIQUID_API_TECHNICAL_GUIDE.md` for comprehensive technical documentation covering:
- Authentication & EIP-712 signing
- Order placement and grouped TP/SL
- Position management strategies
- Common pitfalls and solutions
- Complete code examples

## ⚠️ Risk Warning

These bots use high leverage (20x-40x) and are designed for experienced traders. Always:
- Start with small position sizes
- Understand the strategies before running
- Monitor positions actively
- Use proper risk management

## 🔧 Key Features

- ✅ **Grouped TP/SL Orders**: Orders appear properly in Hyperliquid UI
- ✅ **EIP-712 Signing**: Proper authentication with Hyperliquid API
- ✅ **Position Tracking**: Internal position management for reliability
- ✅ **High Leverage**: Efficient capital utilization (20x-40x)
- ✅ **Real-time Data**: WebSocket and REST API integration
- ✅ **Error Handling**: Robust error handling and position cleanup
- 🆕 **Web Dashboard**: Beautiful real-time web interface for Color Trader
- 🆕 **Visual Trading**: First-of-its-kind screen color detection system

## 🎯 Strategies Explained

### Ultimate Scalping Bot
Monitors price movements and places entry orders with pre-configured TP/SL when price hits target levels. Uses percentage-based targets that scale with asset price.

### Order Book Hunter
Analyzes order book imbalances (bid/ask ratio) and confirms with volume spikes to identify high-probability short-term moves. Perfect for market microstructure trading.

### Experimental Color Trader
Captures a region of your screen and analyzes the dominant color to detect signals from visual indicators. Automatically flips positions based on color changes (green = long, red = short).

---

*All bots have been tested and verified to work correctly with Hyperliquid's mainnet API.*
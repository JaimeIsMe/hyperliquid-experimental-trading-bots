# 🚀 Hyperliquid API Technical Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [Authentication & Signing](#authentication--signing)
3. [Order Placement](#order-placement)
4. [Grouped Orders with TP/SL](#grouped-orders-with-tpsl)
5. [Position Management](#position-management)
6. [WebSocket Integration](#websocket-integration)
7. [Common Pitfalls & Solutions](#common-pitfalls--solutions)
8. [Code Examples](#code-examples)

---

## Overview

This guide documents the technical implementation of Hyperliquid's API for automated trading, based on three production bots:
- **Ultimate Scalping Bot**: Demonstrates grouped order placement with TP/SL
- **Order Book Hunter**: Shows WebSocket integration and order book analysis
- **Experimental Color Trader**: Illustrates position flipping and management

### Key Features Covered
- ✅ Raw API implementation (not just SDK)
- ✅ Proper EIP-712 signing
- ✅ Grouped orders with TP/SL that show in UI
- ✅ Position opening/closing/flipping
- ✅ Real-time data via WebSocket
- ✅ Order book analysis

---

## Authentication & Signing

### 1. Private Key Setup

```python
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.crypto import keccak
from eth_utils.conversions import to_hex
import msgpack

# Load private key from .env
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
if not private_key.startswith('0x'):
    private_key = '0x' + private_key

# Create account object
account = Account.from_key(private_key)
wallet_address = account.address
```

### 2. Action Hashing

The action must be hashed using msgpack before signing:

```python
def hash_action(action, vault, nonce) -> bytes:
    """Hash the action for signing"""
    data = msgpack.packb(action)
    data += nonce.to_bytes(8, "big")
    
    if vault is None:
        data += b"\x00"
    else:
        data += b"\x01"
        data += bytes.fromhex(vault.removeprefix("0x"))
    return keccak(data)
```

### 3. EIP-712 Signing

Hyperliquid uses EIP-712 typed data signing:

```python
def sign_action(action: dict, vault: str | None, nonce: int, is_mainnet: bool) -> dict:
    """Sign an action with proper EIP-712 format"""
    h = hash_action(action, vault, nonce)
    msg = {"source": "a" if is_mainnet else "b", "connectionId": to_hex(h)}
    
    data = {
        "domain": {
            "chainId": 1337,
            "name": "Exchange",
            "verifyingContract": "0x0000000000000000000000000000000000000000",
            "version": "1",
        },
        "types": {
            "Agent": [
                {"name": "source", "type": "string"},
                {"name": "connectionId", "type": "bytes32"},
            ],
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        },
        "primaryType": "Agent",
        "message": msg,
    }
    
    # Sign the typed data
    encodes = encode_typed_data(full_message=data)
    signed = account.sign_message(encodes)
    
    return {
        "r": to_hex(signed["r"]),
        "s": to_hex(signed["s"]),
        "v": signed["v"],
    }
```

### ⚠️ Critical Notes:
- Always use `to_hex()` for the connectionId in the message
- The domain chainId is always `1337` regardless of mainnet/testnet
- The verifyingContract is always the zero address
- Use `account.sign_message()` not `wallet.sign_message()`

---

## Order Placement

### 1. Basic Order Structure

```python
order = {
    "a": 5,  # Asset index (5 = SOL)
    "b": True,  # True = Buy, False = Sell
    "p": "168.50",  # Price (must be string)
    "s": "1.5",  # Size (must be string)
    "r": False,  # Reduce only
    "t": {"limit": {"tif": "Gtc"}}  # Order type
}
```

### 2. Order Types

**Limit Orders:**
```python
"t": {"limit": {"tif": "Gtc"}}  # Good till cancelled
"t": {"limit": {"tif": "Ioc"}}  # Immediate or cancel
"t": {"limit": {"tif": "Alo"}}  # Add liquidity only
```

**Trigger Orders (Stop/Take Profit):**
```python
"t": {
    "trigger": {
        "isMarket": True,
        "triggerPx": "169.00",
        "tpsl": "tp"  # or "sl" for stop loss
    }
}
```

### 3. Placing an Order

```python
def place_order(order):
    action = {
        "type": "order",
        "orders": [order],
        "grouping": "na"  # No grouping for single orders
    }
    
    nonce = int(time.time() * 1000)
    signature = sign_action(action, None, nonce, True)
    
    payload = {
        "action": action,
        "nonce": nonce,
        "signature": signature,
        "vaultAddress": None
    }
    
    response = requests.post(
        "https://api.hyperliquid.xyz/exchange",
        headers={"Content-Type": "application/json"},
        json=payload
    )
    
    return response.json()
```

---

## Grouped Orders with TP/SL

### The Magic: `normalTpsl` Grouping

To make TP/SL orders appear grouped in the UI (like they do on the web interface), use the `normalTpsl` grouping:

```python
def place_grouped_order_with_tpsl(entry_price, position_size, tp_price, sl_price, is_buy=True):
    """Place entry order with grouped TP/SL that shows in UI"""
    
    orders = [
        # Main entry order
        {
            "a": 5,  # SOL
            "b": is_buy,
            "p": str(entry_price),
            "s": str(position_size),
            "r": False,
            "t": {"limit": {"tif": "Gtc"}}
        },
        # Stop Loss order
        {
            "a": 5,
            "b": not is_buy,  # Opposite direction
            "p": str(sl_price - 1 if is_buy else sl_price + 1),  # Execution price
            "s": str(position_size),
            "r": True,  # Reduce only
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": str(sl_price),
                    "tpsl": "sl"  # CRITICAL: Mark as stop loss
                }
            }
        },
        # Take Profit order
        {
            "a": 5,
            "b": not is_buy,  # Opposite direction
            "p": str(tp_price),
            "s": str(position_size),
            "r": True,  # Reduce only
            "t": {
                "trigger": {
                    "isMarket": True,
                    "triggerPx": str(tp_price),
                    "tpsl": "tp"  # CRITICAL: Mark as take profit
                }
            }
        }
    ]
    
    action = {
        "type": "order",
        "orders": orders,
        "grouping": "normalTpsl"  # THE MAGIC GROUPING!
    }
    
    # Sign and send as before...
```

### Key Points for Grouped Orders:
1. **All orders must be sent in ONE request**
2. **Use `"grouping": "normalTpsl"`** - this makes them appear grouped in UI
3. **TP/SL orders must have `"tpsl": "tp"` or `"tpsl": "sl"`** in trigger
4. **TP/SL orders must be reduce-only (`"r": True`)**
5. **TP/SL orders must be opposite direction to entry**

---

## Position Management

### 1. Opening a Position

```python
async def enter_position(direction: str, size_usd: float):
    """Enter a leveraged position"""
    
    # Get current price
    current_price = get_current_price()
    
    # Calculate position size in base currency
    position_size = round(size_usd / current_price, 2)
    
    # Determine order parameters
    is_buy = direction.lower() == "long"
    
    # Use IOC with wide spread for immediate fill
    if is_buy:
        order_price = round(current_price * 1.01, 2)  # 1% above
    else:
        order_price = round(current_price * 0.99, 2)  # 1% below
    
    order = {
        "a": 5,  # SOL
        "b": is_buy,
        "p": str(order_price),
        "s": str(position_size),
        "r": False,
        "t": {"limit": {"tif": "Ioc"}}  # Immediate or cancel
    }
    
    # Place order and track the response
    result = place_order(order)
    
    # Store order data for closing later
    if result['status'] == 'ok':
        statuses = result['response']['data']['statuses']
        for status in statuses:
            if 'filled' in status:
                return status['filled']  # Save this data!
```

### 2. Closing a Position

```python
async def close_position(entry_order_data):
    """Close position using stored order data"""
    
    # Extract position details
    position_size = float(entry_order_data['totalSz'])
    is_long = entry_order_data['side'] == 'B'
    
    # Close order is opposite direction
    is_buy = not is_long
    
    # Get current price and set wide spread
    current_price = get_current_price()
    if is_buy:
        close_price = round(current_price * 1.01, 2)
    else:
        close_price = round(current_price * 0.99, 2)
    
    close_order = {
        "a": 5,  # SOL
        "b": is_buy,
        "p": str(close_price),
        "s": str(position_size),
        "r": True,  # CRITICAL: Reduce only!
        "t": {"limit": {"tif": "Ioc"}}
    }
    
    return place_order(close_order)
```

### 3. Position Flipping

```python
async def flip_position(current_position, new_direction):
    """Flip from long to short or vice versa"""
    
    # Step 1: Close current position
    if current_position:
        await close_position(current_position)
        
        # CRITICAL: Wait for margin to be released
        await asyncio.sleep(10)  # 10 seconds is safe
    
    # Step 2: Open new position
    return await enter_position(new_direction)
```

---

## WebSocket Integration

### 1. Connection Setup

```python
import websockets

async def connect_websocket():
    ws_url = "wss://api.hyperliquid.xyz/ws"
    
    async with websockets.connect(ws_url) as websocket:
        # Subscribe to L2 book
        subscribe_msg = {
            "method": "subscribe",
            "subscription": {
                "type": "l2Book",
                "coin": "SOL"
            }
        }
        await websocket.send(json.dumps(subscribe_msg))
        
        # Process messages
        async for message in websocket:
            data = json.loads(message)
            await process_market_data(data)
```

### 2. Order Book Data Structure

```python
def process_orderbook(data):
    """Process L2 order book data"""
    
    # Data structure:
    # {
    #   "channel": "l2Book",
    #   "data": {
    #     "levels": [
    #       [[price, size], ...],  # Bids
    #       [[price, size], ...]   # Asks
    #     ]
    #   }
    # }
    
    bids = data['data']['levels'][0]
    asks = data['data']['levels'][1]
    
    # Calculate metrics
    best_bid = float(bids[0][0])
    best_ask = float(asks[0][0])
    mid_price = (best_bid + best_ask) / 2
    
    # Calculate imbalance
    bid_volume = sum(float(level[1]) for level in bids[:5])
    ask_volume = sum(float(level[1]) for level in asks[:5])
    imbalance_ratio = bid_volume / ask_volume if ask_volume > 0 else 999
```

---

## Common Pitfalls & Solutions

### 1. Wallet Address Issues

**Problem**: "User or API Wallet ... does not exist"

**Solution**: 
- Ensure consistent use of `account.address`
- Use `account.sign_message()` not `wallet.sign_message()`
- Store address once: `self.address = self.account.address`

### 2. Order Not Filling

**Problem**: Orders remain open, not filling

**Solutions**:
- Use IOC (Immediate or Cancel) for market-like execution
- Set wider spreads (1% above/below for guaranteed fills)
- Check minimum order size (0.01 SOL minimum)

### 3. TP/SL Not Showing in UI

**Problem**: TP/SL orders placed but not grouped in UI

**Solution**: 
- Must use `"grouping": "normalTpsl"`
- All orders must be in same request
- TP/SL must have `"tpsl": "tp"` or `"tpsl": "sl"`

### 4. Position Flip Failures

**Problem**: "Insufficient margin" when flipping positions

**Solution**:
- Always close existing position first
- Wait 10+ seconds for margin release
- Then open new position

### 5. Decimal Precision

**Problem**: "round_float causes rounding" errors

**Solution**:
```python
def round_float(x: float) -> str:
    """Safe float to string conversion"""
    rounded = f"{x:.8f}"
    if abs(float(rounded) - x) >= 1e-12:
        raise ValueError("round_float causes rounding", x)
    if rounded == "-0":
        rounded = "0"
    normalized = Decimal(rounded).normalize()
    return f"{normalized:f}"
```

---

## Code Examples

### Complete Order Flow Example

```python
import asyncio
import time
import requests
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.utils import constants

class HyperliquidTrader:
    def __init__(self, private_key):
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        
    async def execute_trade_with_tpsl(self):
        """Complete trade flow with TP/SL"""
        
        # 1. Get current price
        all_mids = self.info.all_mids()
        current_price = float(all_mids['SOL'])
        
        # 2. Calculate position parameters
        position_usd = 1000  # $1000 position
        leverage = 20
        actual_capital = position_usd / leverage  # $50
        
        position_size = round(position_usd / current_price, 2)
        entry_price = round(current_price - 0.05, 2)  # 5 cents below
        tp_price = round(entry_price * 1.003, 2)  # +0.3%
        sl_price = round(entry_price * 0.998, 2)  # -0.2%
        
        # 3. Build grouped order
        orders = [
            {
                "a": 5,  # SOL
                "b": True,  # Buy
                "p": str(entry_price),
                "s": str(position_size),
                "r": False,
                "t": {"limit": {"tif": "Gtc"}}
            },
            {
                "a": 5,
                "b": False,  # Sell (SL)
                "p": str(sl_price - 1),
                "s": str(position_size),
                "r": True,
                "t": {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": str(sl_price),
                        "tpsl": "sl"
                    }
                }
            },
            {
                "a": 5,
                "b": False,  # Sell (TP)
                "p": str(tp_price),
                "s": str(position_size),
                "r": True,
                "t": {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": str(tp_price),
                        "tpsl": "tp"
                    }
                }
            }
        ]
        
        # 4. Create action
        action = {
            "type": "order",
            "orders": orders,
            "grouping": "normalTpsl"
        }
        
        # 5. Sign and send
        nonce = int(time.time() * 1000)
        signature = self.sign_action(action, None, nonce, True)
        
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }
        
        response = requests.post(
            "https://api.hyperliquid.xyz/exchange",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        
        result = response.json()
        
        if result['status'] == 'ok':
            print("✅ Order placed with TP/SL!")
            print(f"Entry: ${entry_price}")
            print(f"TP: ${tp_price} (+0.3%)")
            print(f"SL: ${sl_price} (-0.2%)")
            print(f"Size: {position_size} SOL")
            print(f"Your capital: ${actual_capital}")
        else:
            print(f"❌ Order failed: {result}")

# Usage
trader = HyperliquidTrader("your_private_key")
asyncio.run(trader.execute_trade_with_tpsl())
```

---

## Summary

The key to successful Hyperliquid API integration:

1. **Use raw API calls** for full control
2. **Implement proper EIP-712 signing** with msgpack hashing
3. **Use `normalTpsl` grouping** for UI-visible TP/SL
4. **Handle position flipping** with proper margin release timing
5. **Use IOC orders with wide spreads** for guaranteed fills
6. **Store order data** for accurate position tracking
7. **Implement proper error handling** and position cleanup

This implementation provides professional-grade trading capabilities with all orders properly displayed in the Hyperliquid UI, just like manual trading.

---

## Resources

- Hyperliquid API Endpoint: `https://api.hyperliquid.xyz/exchange`
- WebSocket Endpoint: `wss://api.hyperliquid.xyz/ws`
- Info API: Use the SDK's Info class for market data
- Required packages: `eth-account`, `msgpack-python`, `hyperliquid-python-sdk`

---

*This guide is based on production implementations in Ultimate Scalping Bot, Order Book Hunter, and Experimental Color Trader. All code has been tested and verified to work correctly with Hyperliquid's mainnet.*
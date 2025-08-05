#!/usr/bin/env python3
"""
🎯 ORDER BOOK IMBALANCE HUNTER
===============================
Detects order book imbalances + volume spikes for high-probability scalps!

Strategy:
- Monitor L2 order book for bid/ask imbalances
- Confirm with volume spikes
- Enter fast, exit faster
- The perfect market microstructure edge!
"""

import asyncio
import websockets
import json
import time
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
from collections import deque
import requests
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.crypto import keccak
from eth_utils.conversions import to_hex
import msgpack
from decimal import Decimal
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import os
from dotenv import load_dotenv

class OrderBookHunter:
    def __init__(self):
        """Initialize the Order Book Imbalance Hunter"""
        print("🎯 ORDER BOOK IMBALANCE HUNTER INITIALIZING...")
        print("=" * 60)
        
        # Load credentials
        self.load_credentials()
        
        # Initialize Hyperliquid clients
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = Exchange(self.account, constants.MAINNET_API_URL)
        
        # Strategy parameters
        self.coin = 'SOL'
        self.asset_index = 5  # SOL
        self.leverage = 20
        
        # Imbalance detection parameters
        self.imbalance_threshold = 3.0  # 3:1 ratio for strong imbalance
        self.volume_spike_threshold = 1.5  # 1.5x average volume spike (more realistic)
        self.min_spread_bps = 0  # No minimum spread - SOL is super liquid
        
        # Position sizing (with 20x leverage)
        self.base_position_usd = 300.0  # Base position size (leveraged)
        self.max_position_usd = 500.0  # Max when strong signal (leveraged)
        self.base_capital_required = 15.0  # Only $15 of our money at 20x!
        self.max_capital_required = 25.0  # Only $25 of our money at 20x!
        
        # Risk management (percentage-based)
        self.tp_percentage = 0.25  # 0.25% take profit
        self.sl_percentage = 0.10  # 0.10% stop loss (2.5:1 RR)
        self.time_stop_seconds = 30  # Exit if no movement
        
        # Data tracking
        self.orderbook_history = deque(maxlen=50)  # Last 50 snapshots
        self.volume_history = deque(maxlen=30)  # 30 seconds of volume
        self.last_update_time = 0
        self.position_open = False
        self.entry_time = None
        self.entry_price = None
        self.entry_order_data = None  # Store the filled order data
        self.position_direction = None  # 'long' or 'short'
        self.position_size = None  # Actual filled size
        
        # WebSocket URL for real-time data
        self.ws_url = "wss://api.hyperliquid-testnet.xyz/ws"  # Will switch to mainnet
        
    def load_credentials(self):
        """Load credentials from .env file"""
        env_vars = {}
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
        
        private_key = env_vars.get('HYPERLIQUID_PRIVATE_KEY')
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        print(f'🔑 Wallet: {self.address}')
        
    def round_float(self, x: float) -> str:
        """Round float to string with proper precision"""
        rounded = f"{x:.8f}"
        if abs(float(rounded) - x) >= 1e-12:
            raise ValueError("round_float causes rounding", x)
        if rounded == "-0":
            rounded = "0"
        normalized = Decimal(rounded).normalize()
        return f"{normalized:f}"
    
    def get_current_price(self):
        """Get current SOL price"""
        try:
            all_mids = self.info.all_mids()
            sol_price = float(all_mids[self.coin])
            return sol_price
        except Exception as e:
            print(f"❌ Error getting current price: {e}")
            return None
    
    def hash_action(self, action, vault, nonce) -> bytes:
        """Hash the action for signing"""
        data = msgpack.packb(action)
        data += nonce.to_bytes(8, "big")
        
        if vault is None:
            data += b"\x00"
        else:
            data += b"\x01"
            data += bytes.fromhex(vault.removeprefix("0x"))
        return keccak(data)
    
    def sign_inner(self, data: dict) -> dict:
        """Sign the typed data"""
        encodes = encode_typed_data(full_message=data)
        signed = self.account.sign_message(encodes)
        return {
            "r": to_hex(signed["r"]),
            "s": to_hex(signed["s"]),
            "v": signed["v"],
        }
    
    def sign_action(self, action: dict, vault: str | None, nonce: int, is_mainnet: bool) -> dict:
        """Sign an action with proper EIP-712 format"""
        h = self.hash_action(action, vault, nonce)
        msg = {"source": "a" if is_mainnet else "b", "connectionId": h}
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
        return self.sign_inner(data)
    
    def place_order_raw(self, order):
        """Place order using raw API"""
        action = {
            "type": "order",
            "orders": [order],
            "grouping": "na"  # No grouping for simple orders
        }
        
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
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "error", "error": f"HTTP {response.status_code}"}
    
    def place_grouped_order(self, orders):
        """Place grouped order with normalTpsl grouping"""
        action = {
            "type": "order",
            "orders": orders,
            "grouping": "normalTpsl"  # THE MAGIC GROUPING!
        }
        
        nonce = int(time.time() * 1000)
        signature = self.sign_action(action, None, nonce, True)
        
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }
        
        print("🚀 Placing grouped order with TP/SL...")
        response = requests.post(
            "https://api.hyperliquid.xyz/exchange",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'ok':
                statuses = result.get('response', {}).get('data', {}).get('statuses', [])
                print(f'📊 Order statuses: {statuses}')
            return result
        else:
            return {"status": "error", "error": f"HTTP {response.status_code}"}
        
    async def connect_websocket(self):
        """Connect to Hyperliquid WebSocket for real-time data"""
        # For mainnet
        ws_url = "wss://api.hyperliquid.xyz/ws"
        
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to L2 book and trades
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "l2Book",
                    "coin": self.coin
                }
            }
            await websocket.send(json.dumps(subscribe_msg))
            
            # Also subscribe to trades for volume
            trades_msg = {
                "method": "subscribe", 
                "subscription": {
                    "type": "trades",
                    "coin": self.coin
                }
            }
            await websocket.send(json.dumps(trades_msg))
            
            print(f"✅ Connected to WebSocket! Hunting for imbalances...")
            
            # Process messages
            async for message in websocket:
                data = json.loads(message)
                await self.process_market_data(data)
                
    async def process_market_data(self, data: dict):
        """Process incoming market data"""
        if data.get('channel') == 'l2Book':
            await self.analyze_orderbook(data['data'])
        elif data.get('channel') == 'trades':
            self.update_volume(data['data'])
            
    async def analyze_orderbook(self, orderbook_data: dict):
        """Analyze order book for imbalances"""
        try:
            # Extract bid/ask data
            bids = orderbook_data.get('levels', [[], []])[0]  # [[price, size], ...]
            asks = orderbook_data.get('levels', [[], []])[1]
            
            if not bids or not asks:
                return
                
            # Calculate total bid/ask sizes (top 5 levels)
            bid_size = sum(float(level[1]) for level in bids[:5])
            ask_size = sum(float(level[1]) for level in asks[:5])
            
            # Calculate imbalance ratio
            if ask_size > 0:
                imbalance_ratio = bid_size / ask_size
            else:
                imbalance_ratio = 999  # Extreme bullish
                
            # Get best bid/ask
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2
            spread_bps = ((best_ask - best_bid) / mid_price) * 10000
            
            # Store snapshot
            snapshot = {
                'time': time.time(),
                'imbalance_ratio': imbalance_ratio,
                'bid_size': bid_size,
                'ask_size': ask_size,
                'mid_price': mid_price,
                'spread_bps': spread_bps,
                'best_bid': best_bid,
                'best_ask': best_ask
            }
            self.orderbook_history.append(snapshot)
            
            # Check for trading opportunity
            await self.check_entry_conditions(snapshot)
            
            # Display current state
            direction = "🟢 BULLISH" if imbalance_ratio > 1 else "🔴 BEARISH"
            # Show history building progress
            history_status = f"[{len(self.orderbook_history)}/30]" if len(self.orderbook_history) < 30 else ""
            
            print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Price: ${mid_price:.2f} | "
                  f"Imbalance: {imbalance_ratio:.2f}:1 {direction} | "
                  f"Spread: {spread_bps:.1f}bps | "
                  f"Volume: {self.get_recent_volume():.2f}x avg {history_status}", 
                  end='', flush=True)
                  
        except Exception as e:
            print(f"\n❌ Error analyzing orderbook: {e}")
            
    def update_volume(self, trades: List[dict]):
        """Update volume tracking from trades"""
        for trade in trades:
            volume_usd = float(trade['sz']) * float(trade['px'])
            self.volume_history.append({
                'time': time.time(),
                'volume': volume_usd
            })
            
    def get_recent_volume(self) -> float:
        """Get recent volume vs average using order book changes as proxy"""
        if len(self.orderbook_history) < 10:
            return 1.0
            
        # Calculate volume proxy from order book size changes
        volume_proxy = 0
        for i in range(1, min(10, len(self.orderbook_history))):
            curr = self.orderbook_history[-i]
            prev = self.orderbook_history[-i-1]
            
            # Volume proxy = change in total book size + price movement
            size_change = abs((curr['bid_size'] + curr['ask_size']) - 
                            (prev['bid_size'] + prev['ask_size']))
            price_change = abs(curr['mid_price'] - prev['mid_price'])
            
            # Combine size change and price volatility
            volume_proxy += size_change + (price_change * 1000)  # Scale price change
            
        # Compare to longer-term average
        if len(self.orderbook_history) >= 30:
            avg_proxy = 0
            for i in range(10, 30):
                if i < len(self.orderbook_history) - 1:
                    curr = self.orderbook_history[-i]
                    prev = self.orderbook_history[-i-1]
                    size_change = abs((curr['bid_size'] + curr['ask_size']) - 
                                    (prev['bid_size'] + prev['ask_size']))
                    price_change = abs(curr['mid_price'] - prev['mid_price'])
                    avg_proxy += size_change + (price_change * 1000)
            
            avg_proxy = avg_proxy / 20 if avg_proxy > 0 else 1
            return (volume_proxy / 10) / avg_proxy if avg_proxy > 0 else 1.0
        
        return 1.0
        
    async def check_entry_conditions(self, snapshot: dict):
        """Check if conditions are met for entry"""
        if self.position_open:
            await self.manage_position()
            return
            
        # Get imbalance strength
        imbalance = snapshot['imbalance_ratio']
        volume_spike = self.get_recent_volume()
        
        # Check for LONG opportunity
        if (imbalance > self.imbalance_threshold and 
            volume_spike > self.volume_spike_threshold and
            snapshot['spread_bps'] >= self.min_spread_bps):
            
            print(f"\n\n🚀 LONG SIGNAL DETECTED!")
            print(f"   Imbalance: {imbalance:.2f}:1 (Bullish)")
            print(f"   Volume: {volume_spike:.1f}x average")
            print(f"   Entry: ${snapshot['best_ask']:.2f}")
            
            await self.enter_position('long', snapshot)
            
        # Check for SHORT opportunity (bearish when ask_size > bid_size, so ratio < 1)
        elif (imbalance < 0.5 and  # More reasonable threshold for shorts
              volume_spike > self.volume_spike_threshold and
              snapshot['spread_bps'] >= self.min_spread_bps):
            
            print(f"\n\n🔴 SHORT SIGNAL DETECTED!")
            print(f"   Imbalance: {imbalance:.2f}:1 (Bearish)")
            print(f"   Volume: {volume_spike:.1f}x average")
            print(f"   Entry: ${snapshot['best_bid']:.2f}")
            
            await self.enter_position('short', snapshot)
            
    async def enter_position(self, direction: str, snapshot: dict):
        """Enter a position based on signal"""
        try:
            # Calculate position size based on signal strength
            imbalance_strength = abs(snapshot['imbalance_ratio'] - 1)
            size_multiplier = min(imbalance_strength / 2, 1.67)  # Max 1.67x
            position_usd = self.base_position_usd * size_multiplier
            position_usd = min(position_usd, self.max_position_usd)
            
            # Get entry price
            if direction == 'long':
                entry_price = snapshot['best_ask']
                tp_price = round(entry_price * (1 + self.tp_percentage / 100), 2)
                sl_price = round(entry_price * (1 - self.sl_percentage / 100), 2)
                is_buy = True
            else:
                entry_price = snapshot['best_bid']
                tp_price = round(entry_price * (1 - self.tp_percentage / 100), 2)
                sl_price = round(entry_price * (1 + self.sl_percentage / 100), 2)
                is_buy = False
                
            # Calculate position size in SOL
            position_size = round(position_usd / entry_price, 2)
            
            # Calculate actual capital required with leverage
            capital_required = position_usd / self.leverage
            
            print(f"\n📊 EXECUTING {direction.upper()} TRADE:")
            print(f"   Size: {position_size} SOL (${position_usd:.0f} position)")
            print(f"   Leverage: {self.leverage}x")
            print(f"   Your Capital: ${capital_required:.2f} (controls ${position_usd:.0f}!)")
            print(f"   TP: ${tp_price:.2f} ({'+' if is_buy else '-'}{self.tp_percentage}%)")
            print(f"   SL: ${sl_price:.2f} ({'-' if is_buy else '+'}{self.sl_percentage}%)")
            
            # Build grouped order with TP/SL like the working bot!
            orders = [
                # Main entry order
                {
                    "a": self.asset_index,
                    "b": is_buy,
                    "p": self.round_float(entry_price + (0.10 if is_buy else -0.10)),  # Slightly worse price to ensure fill
                    "s": self.round_float(position_size),
                    "r": False,  # Not reduce only
                    "t": {"limit": {"tif": "Ioc"}}  # Immediate or cancel
                },
                # Stop Loss order
                {
                    "a": self.asset_index,
                    "b": not is_buy,  # Opposite direction
                    "p": self.round_float(sl_price + 1 if is_buy else sl_price - 1),  # Execution price beyond trigger
                    "s": self.round_float(position_size),
                    "r": True,  # Reduce only
                    "t": {
                        "trigger": {
                            "isMarket": True,
                            "triggerPx": self.round_float(sl_price),
                            "tpsl": "sl"  # Stop Loss marker
                        }
                    }
                },
                # Take Profit order
                {
                    "a": self.asset_index,
                    "b": not is_buy,  # Opposite direction
                    "p": self.round_float(tp_price),
                    "s": self.round_float(position_size),
                    "r": True,  # Reduce only
                    "t": {
                        "trigger": {
                            "isMarket": True,
                            "triggerPx": self.round_float(tp_price),
                            "tpsl": "tp"  # Take Profit marker
                        }
                    }
                }
            ]
            
            order_result = self.place_grouped_order(orders)
            
            if order_result.get('status') == 'ok':
                statuses = order_result.get('response', {}).get('data', {}).get('statuses', [])
                
                # Check if main order has error
                if statuses and isinstance(statuses[0], dict) and 'error' in statuses[0]:
                    print(f"❌ Order error: {statuses[0]['error']}")
                    print(f"   Debug - Entry: ${entry_price}, TP: ${tp_price}, SL: ${sl_price}")
                else:
                    # Store order data for position management
                    if statuses and len(statuses) >= 1:
                        main_status = statuses[0]
                        if 'filled' in main_status:
                            self.entry_order_data = main_status
                            self.position_size = float(main_status['filled']['totalSz'])
                            self.position_direction = direction
                        
                    self.position_open = True
                    self.entry_time = time.time()
                    self.entry_price = entry_price
                    print("✅ Position opened with TP/SL grouped!")
                    if self.entry_order_data:
                        print(f"   Entry Order ID: {self.entry_order_data['filled']['oid']}")
                        print(f"   Filled Size: {self.position_size} SOL")
                        print(f"   Direction: {self.position_direction.upper()}")
            else:
                print("❌ Order failed:", order_result)
                
        except Exception as e:
            print(f"❌ Error entering position: {e}")
            
    async def manage_position(self):
        """Manage open position"""
        if not self.position_open:
            return
            
        # Check time stop
        if time.time() - self.entry_time > self.time_stop_seconds:
            print(f"\n⏰ Time stop triggered! Closing position...")
            await self.close_position()
            
    async def close_position(self):
        """Close current position using order data approach"""
        try:
            if not self.position_open or not self.entry_order_data:
                print("✅ No position to close")
                return
                
            # Extract data from the original order
            filled_data = self.entry_order_data['filled']
            original_size = float(filled_data['totalSz'])
            original_price = float(filled_data['avgPx'])
            order_id = filled_data['oid']
            
            print(f"🔄 Closing position using order data:")
            print(f"   Original Order ID: {order_id}")
            print(f"   Original Size: {original_size} SOL")
            print(f"   Original Price: ${original_price:.2f}")
            print(f"   Direction: {self.position_direction}")
            
            # First, cancel any existing TP/SL orders
            cancel_action = {
                "type": "cancel",
                "cancels": [{"a": self.asset_index, "o": ""}]  # Cancel all orders for SOL
            }
            
            nonce = int(time.time() * 1000)
            signature = self.sign_action(cancel_action, None, nonce, True)
            
            cancel_payload = {
                "action": cancel_action,
                "nonce": nonce,
                "signature": signature,
                "vaultAddress": None
            }
            
            requests.post(
                "https://api.hyperliquid.xyz/exchange",
                headers={"Content-Type": "application/json"},
                json=cancel_payload
            )
            
            # Get current price for market close
            current_price = self.get_current_price()
            if not current_price:
                print("❌ Could not get current price")
                return
            
            # Determine opposite direction to close
            is_buy = (self.position_direction == 'short')  # If we went long, sell to close
            
            # Market close with wide spread to ensure fill
            if is_buy:
                close_price = round(current_price + 0.50, 2)  # Buy high
            else:
                close_price = round(current_price - 0.50, 2)  # Sell low
                
            print(f"   Close Direction: {'BUY' if is_buy else 'SELL'}")
            print(f"   Close Price: ${close_price:.2f}")
            print(f"   Close Size: {original_size}")
            
            # Place the close order
            close_order = {
                "a": self.asset_index,
                "b": is_buy,
                "p": self.round_float(close_price),
                "s": self.round_float(original_size),
                "r": True,  # Reduce only
                "t": {"limit": {"tif": "Ioc"}}  # Immediate or cancel
            }
            
            result = self.place_order_raw(close_order)
            
            if result.get('status') == 'ok':
                print("✅ Position closed successfully!")
            else:
                print(f"❌ Failed to close position: {result}")
                
        except Exception as e:
            print(f"❌ Error closing position: {e}")
            
        finally:
            # Always reset position tracking
            self.position_open = False
            self.entry_time = None
            self.entry_price = None
            self.entry_order_data = None
            self.position_direction = None
            self.position_size = None
            
    async def run(self):
        """Main bot loop"""
        print("\n🎯 STARTING ORDER BOOK IMBALANCE HUNTER!")
        print(f"📊 Strategy: {self.imbalance_threshold}:1 imbalance + "
              f"{self.volume_spike_threshold}x volume spike")
        print(f"💰 Position: ${self.base_position_usd}-${self.max_position_usd} "
              f"(only ${self.base_capital_required}-${self.max_capital_required} of YOUR money!)")
        print(f"⚡ Leverage: {self.leverage}x (Hyperliquid power!)")
        print(f"🎯 TP: {self.tp_percentage}% | SL: {self.sl_percentage}%")
        print("=" * 60)
        
        # For now, use REST API polling (WebSocket implementation above for future)
        while True:
            try:
                # Get L2 book
                l2_data = self.info.l2_snapshot(self.coin)
                
                # Convert to expected format
                orderbook_data = {
                    'levels': [
                        [[str(level['px']), str(level['sz'])] for level in l2_data['levels'][0]],
                        [[str(level['px']), str(level['sz'])] for level in l2_data['levels'][1]]
                    ]
                }
                
                # Analyze
                await self.analyze_orderbook(orderbook_data)
                
                # Small delay to not overwhelm API
                await asyncio.sleep(1.0)  # Increased to 1 second for stability
                
            except KeyboardInterrupt:
                print("\n\n👋 Shutting down hunter...")
                break
            except Exception as e:
                # Only print error if it's not a common connection issue
                if "Connection aborted" not in str(e):
                    print(f"\n❌ Error in main loop: {e}")
                await asyncio.sleep(2)  # Wait longer after errors
                
if __name__ == "__main__":
    hunter = OrderBookHunter()
    asyncio.run(hunter.run())
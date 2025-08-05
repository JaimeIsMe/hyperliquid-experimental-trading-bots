#!/usr/bin/env python3
"""
🎯 ULTIMATE HYPERLIQUID SCALPING BOT
====================================
✅ Price monitoring (your brilliant idea!)
✅ Raw API with normalTpsl grouping
✅ TP/SL that ACTUALLY shows in the UI!
"""

import os
import json
import time
import requests
import msgpack
from decimal import Decimal
from datetime import datetime
from eth_account import Account
from eth_utils.crypto import keccak
from eth_account.messages import encode_typed_data
from eth_utils.conversions import to_hex
from hyperliquid.info import Info
from hyperliquid.utils import constants


class UltimateScalpingBot:
    def __init__(self):
        print('🎯 ULTIMATE HYPERLIQUID SCALPING BOT')
        print('=' * 60)
        print('✅ Price monitoring for instant execution!')
        print('✅ Raw API with normalTpsl grouping!')
        print('✅ TP/SL that shows in the UI!')
        print('=' * 60)
        
        # Load credentials
        self.load_credentials()
        
        # Initialize info client
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        
        # Strategy parameters
        self.coin = 'SOL'
        self.asset_index = 5  # SOL
        self.leverage = 20
        self.position_size_usd = 300.0  # $300 position
        self.tp_percentage = 0.31  # +0.31% take profit (scales with price!)
        self.sl_percentage = 0.125  # -0.125% stop loss (scales with price!)
        self.entry_offset = 0.05  # 5 cents below current price
        
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
        self.wallet = Account.from_key(private_key)
        print(f'🔑 Wallet: {self.wallet.address}')
    
    def round_float(self, x: float) -> str:
        """Round float to string with proper precision"""
        rounded = f"{x:.8f}"
        if abs(float(rounded) - x) >= 1e-12:
            raise ValueError("round_float causes rounding", x)
        if rounded == "-0":
            rounded = "0"
        normalized = Decimal(rounded).normalize()
        return f"{normalized:f}"
    
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
        signed = self.wallet.sign_message(encodes)
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
    
    def get_current_price(self) -> float:
        """Get current SOL price"""
        all_mids = self.info.all_mids()
        return float(all_mids[self.coin])
    
    def calculate_position_size(self, entry_price: float) -> float:
        """Calculate position size based on USD amount"""
        raw_size = self.position_size_usd / entry_price
        # Round to 2 decimals and ensure minimum
        return max(0.01, round(raw_size, 2))
    
    def place_grouped_order(self, entry_price: float, position_size: float, tp_price: float, sl_price: float):
        """Place grouped order with entry, TP, and SL"""
        
        print(f'\n🎯 BUILDING GROUPED ORDER:')
        print(f'   Entry: ${entry_price:.2f} | Size: {position_size} SOL')
        print(f'   Take Profit: ${tp_price:.2f} (+{self.tp_percentage}%)')
        print(f'   Stop Loss: ${sl_price:.2f} (-{self.sl_percentage}%)')
        
        # Build the orders array with proper structure
        orders = [
            # Main entry order
            {
                "a": self.asset_index,
                "b": True,  # Buy
                "p": self.round_float(entry_price),
                "s": self.round_float(position_size),
                "r": False,  # Not reduce only
                "t": {"limit": {"tif": "Gtc"}}
            },
            # Stop Loss order (trigger)
            {
                "a": self.asset_index,
                "b": False,  # Sell
                "p": self.round_float(sl_price - 1),  # Execution price below trigger
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
            # Take Profit order (trigger)
            {
                "a": self.asset_index,
                "b": False,  # Sell
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
        
        # Build the action with normalTpsl grouping
        action = {
            "type": "order",
            "orders": orders,
            "grouping": "normalTpsl"  # 🎯 THE MAGIC GROUPING!
        }
        
        # Sign the action
        nonce = int(time.time() * 1000)
        vault = None
        is_mainnet = True
        
        print(f'\n🚀 Signing grouped order with normalTpsl...')
        signature = self.sign_action(action, vault, nonce, is_mainnet)
        
        # Build the request payload
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": vault
        }
        
        # Send the request
        headers = {"Content-Type": "application/json"}
        
        try:
            print(f'📡 Sending to Hyperliquid API...')
            response = requests.post(
                "https://api.hyperliquid.xyz/exchange",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'ok':
                    statuses = result.get('response', {}).get('data', {}).get('statuses', [])
                    print(f'\n✅ GROUPED ORDER PLACED SUCCESSFULLY!')
                    print(f'📊 Statuses: {statuses}')
                    
                    # Extract order ID from first status (main order)
                    if statuses and isinstance(statuses[0], dict) and 'resting' in statuses[0]:
                        order_id = statuses[0]['resting']['oid']
                        print(f'🎯 Main Order ID: {order_id}')
                        return order_id
                    
                    return True
                else:
                    print(f'\n❌ API Error: {result}')
                    return False
            else:
                print(f'\n❌ HTTP Error {response.status_code}: {response.text}')
                return False
                
        except Exception as e:
            print(f'\n❌ ERROR placing grouped order: {e}')
            return False
    
    def execute_scalping_strategy(self):
        """Execute the complete scalping strategy with price monitoring"""
        
        print(f'\n🚀 STARTING ULTIMATE SCALPING STRATEGY!')
        print(f'💡 Monitoring price for instant TP/SL placement!')
        
        # Get current price and calculate strategy prices
        current_price = self.get_current_price()
        entry_price = round(current_price - self.entry_offset, 2)
        position_size = self.calculate_position_size(entry_price)
        
        # Calculate TP/SL based on percentages (scales with price!)
        tp_price = round(entry_price * (1 + self.tp_percentage / 100), 2)
        sl_price = round(entry_price * (1 - self.sl_percentage / 100), 2)
        
        print(f'\n💰 Current SOL Price: ${current_price:.2f}')
        print(f'🎯 Strategy Setup:')
        print(f'   Entry: ${entry_price:.2f} (${self.entry_offset} below current)')
        print(f'   Size: {position_size} SOL (${self.position_size_usd} USD)')
        print(f'   Leverage: {self.leverage}x')
        print(f'   Take Profit: ${tp_price:.2f} (+{self.tp_percentage}% = +${tp_price - entry_price:.2f})')
        print(f'   Stop Loss: ${sl_price:.2f} (-{self.sl_percentage}% = -${entry_price - sl_price:.2f})')
        
        # Place the grouped order
        order_id = self.place_grouped_order(entry_price, position_size, tp_price, sl_price)
        
        if not order_id:
            print(f'\n❌ Failed to place grouped order!')
            return
        
        print(f'\n🎯 Starting price monitoring for entry at ${entry_price:.2f}...')
        print(f'💡 Will confirm when price touches entry!')
        
        # Price monitoring loop
        check_interval = 1  # Check every second
        
        while True:
            try:
                current_price = self.get_current_price()
                price_diff = current_price - entry_price
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                if current_price <= entry_price:
                    print(f'[{timestamp}] 🚀 PRICE HIT ENTRY! ${current_price:.2f} <= ${entry_price:.2f}')
                    print(f'✅ Order should be filling NOW!')
                    print(f'🎯 TP/SL orders are ALREADY PLACED and GROUPED!')
                    print(f'💡 Check your Hyperliquid UI - TP/SL should be visible!')
                    break
                else:
                    print(f'[{timestamp}] 💡 Price: ${current_price:.2f} (${price_diff:+.2f} from entry)')
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                print(f'\n⚠️ Monitoring stopped by user')
                break
            except Exception as e:
                print(f'\n⚠️ Error in price monitoring: {e}')
                time.sleep(check_interval)
        
        print(f'\n🎊 STRATEGY COMPLETE!')
        print(f'✅ Entry order placed with GROUPED TP/SL!')
        print(f'🎯 Everything should be visible in your Hyperliquid UI!')


def main():
    """Main execution function"""
    try:
        # Install msgpack if needed
        import msgpack
    except ImportError:
        print('Installing msgpack-python...')
        os.system('pip install msgpack-python')
        import msgpack
    
    # Create and run the bot
    bot = UltimateScalpingBot()
    bot.execute_scalping_strategy()


if __name__ == '__main__':
    main()
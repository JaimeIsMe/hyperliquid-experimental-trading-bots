#!/usr/bin/env python3
"""
🎨 EXPERIMENTAL COLOR TRADER BOT 🤖
================================

This bot uses SCREEN COLOR DETECTION to trade!
- 🟢 GREEN region = GO LONG
- 🔴 RED region = GO SHORT

The bot captures a region of your screen and analyzes the dominant color
to determine trading signals from your secret indicator!

Author: AI Assistant + User Collaboration
Strategy: Screen Color Detection Trading
"""

import asyncio
import pyautogui
import numpy as np
from PIL import Image
import cv2
import time
import os
import json
import requests
import msgpack
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils.crypto import keccak
from eth_utils.conversions import to_hex

class ExperimentalColorTrader:
    def __init__(self):
        """Initialize the Experimental Color Trader"""
        print("🎨 EXPERIMENTAL COLOR TRADER INITIALIZING...")
        
        # Load credentials
        self.load_credentials()
        
        # Screen capture settings
        self.screen_region = None  # Will be set during calibration
        self.capture_width = 100   # Width of capture region
        self.capture_height = 100  # Height of capture region
        
        # Color detection settings
        self.green_target = (76, 175, 80)    # Target green RGB 
        self.red_target = (241, 147, 65)     # Target red RGB (updated from your actual indicator!)
        self.color_tolerance = 80             # Increased tolerance for better matching
        
        # Trading settings
        self.position_usd = 4000.0           # $4000 position (40x leverage)
        self.leverage = 40                   # 40x leverage  
        self.actual_capital = self.position_usd / self.leverage  # $100 of actual capital
        
        # Position tracking
        self.current_position = None         # "long", "short", or None
        self.position_open = False
        self.entry_order_data = None
        self.position_size = None
        self.position_direction = None
        
        # Current signal tracking
        self.current_signal = None           # "LONG", "SHORT", or None
        self.last_signal_time = 0
        self.signal_cooldown = 2.0           # Wait 2 seconds between signal checks
        
        # Animation
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self.spinner_index = 0
        
        print(f"💰 Position Size: ${self.position_usd:,.0f} (${self.actual_capital:.0f} of YOUR money)")
        print(f"🎯 Leverage: {self.leverage}x")
        print(f"🎨 Color Targets: 🟢 RGB{self.green_target} | 🔴 RGB{self.red_target}")
        
    def load_credentials(self):
        """Load API credentials from .env file"""
        load_dotenv()
        
        self.private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        if not self.private_key:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY not found in .env file")
        
        if not self.private_key.startswith('0x'):
            self.private_key = '0x' + self.private_key
        
        # Create account and wallet objects
        self.account = Account.from_key(self.private_key)
        self.wallet = self.account  # Ensure consistency
        self.address = self.account.address  # Store address like order_book_hunter
        
        # Initialize Hyperliquid clients
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)
        self.exchange = Exchange(self.account, constants.MAINNET_API_URL)
        
        print(f"✅ Wallet loaded: {self.address}")
        
    def round_float(self, value: float, decimals: int = 2) -> str:
        """Round float to string with proper precision"""
        if decimals == 0:
            return str(int(round(value)))
        return f"{value:.{decimals}f}"
    
    def get_current_price(self) -> Optional[float]:
        """Get current SOL price"""
        try:
            all_mids = self.info.all_mids()
            if 'SOL' in all_mids:
                return float(all_mids['SOL'])
            return None
        except Exception as e:
            print(f"❌ Error getting price: {e}")
            return None
    
    def calibrate_screen_region(self):
        """Interactive calibration to set the screen region to monitor"""
        print("\n🎯 SCREEN REGION CALIBRATION")
        print("=" * 50)
        print("We need to set up the screen region to monitor for color changes.")
        print()
        print("Instructions:")
        print("1. Open your trading indicator on screen")
        print("2. Make sure the color signal is visible")
        print("3. We'll help you select the right region to monitor")
        print()
        
        # Get screen dimensions
        screen_width, screen_height = pyautogui.size()
        print(f"📺 Screen Size: {screen_width} x {screen_height}")
        print()
        
        while True:
            try:
                print("Enter the screen region coordinates:")
                print("(This is the rectangular area where your indicator shows green/red)")
                print()
                
                x = int(input("📍 X coordinate (left edge): "))
                y = int(input("📍 Y coordinate (top edge): "))
                width = int(input("📏 Width: "))
                height = int(input("📏 Height: "))
                
                # Validate coordinates
                if x < 0 or y < 0 or x + width > screen_width or y + height > screen_height:
                    print("❌ Coordinates are outside screen bounds. Please try again.")
                    continue
                
                self.screen_region = (x, y, width, height)
                self.capture_width = width
                self.capture_height = height
                
                print(f"✅ Region set: ({x}, {y}) size {width}x{height}")
                
                # Test capture
                print("\n🧪 Testing screen capture...")
                test_image = self.capture_screen_region()
                if test_image is not None:
                    dominant_color = self.get_dominant_color(test_image)
                    signal = self.detect_color_signal(dominant_color)
                    
                    print(f"🎨 Current dominant color: RGB{dominant_color}")
                    print(f"🚦 Detected signal: {signal}")
                    
                    confirm = input("\n✅ Does this look correct? (y/n): ").lower().strip()
                    if confirm == 'y':
                        break
                    else:
                        print("Let's try different coordinates...")
                        continue
                else:
                    print("❌ Failed to capture screen. Please try again.")
                    continue
                    
            except ValueError:
                print("❌ Please enter valid numbers.")
                continue
            except Exception as e:
                print(f"❌ Error during calibration: {e}")
                continue
        
        print(f"\n🎯 Calibration complete! Monitoring region: {self.screen_region}")
    
    def capture_screen_region(self) -> Optional[np.ndarray]:
        """Capture the specified screen region"""
        try:
            if self.screen_region is None:
                print("❌ Screen region not set. Run calibration first.")
                return None
            
            # Capture screenshot of the region
            screenshot = pyautogui.screenshot(region=self.screen_region)
            
            # Convert PIL image to numpy array
            img_array = np.array(screenshot)
            
            return img_array
            
        except Exception as e:
            print(f"❌ Error capturing screen: {e}")
            return None
    
    def get_dominant_color(self, image: np.ndarray) -> Tuple[int, int, int]:
        """Get the dominant color in the image region"""
        try:
            # Reshape image to list of pixels
            pixels = image.reshape(-1, 3)
            
            # Use k-means clustering to find dominant color
            from sklearn.cluster import KMeans
            
            # Use 3 clusters to find main colors
            kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
            kmeans.fit(pixels)
            
            # Get the cluster centers (dominant colors)
            colors = kmeans.cluster_centers_.astype(int)
            
            # Get the most frequent cluster (dominant color)
            labels = kmeans.labels_
            unique, counts = np.unique(labels, return_counts=True)
            dominant_cluster = unique[np.argmax(counts)]
            dominant_color = colors[dominant_cluster]
            
            return tuple(dominant_color)
            
        except ImportError:
            # Fallback: simple average if sklearn not available
            print("⚠️  sklearn not available, using simple average")
            avg_color = np.mean(image.reshape(-1, 3), axis=0).astype(int)
            return tuple(avg_color)
        except Exception as e:
            print(f"❌ Error getting dominant color: {e}")
            # Return a neutral color
            return (128, 128, 128)
    
    def color_distance(self, color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> float:
        """Calculate Euclidean distance between two RGB colors"""
        return np.sqrt(sum((c1 - c2) ** 2 for c1, c2 in zip(color1, color2)))
    
    def detect_color_signal(self, dominant_color: Tuple[int, int, int]) -> Optional[str]:
        """Detect trading signal based on dominant color"""
        try:
            green_distance = self.color_distance(dominant_color, self.green_target)
            red_distance = self.color_distance(dominant_color, self.red_target)
            
            # Check if color is close enough to either target
            if green_distance <= self.color_tolerance and green_distance < red_distance:
                return "LONG"
            elif red_distance <= self.color_tolerance and red_distance < green_distance:
                return "SHORT"
            else:
                return None  # No clear signal
                
        except Exception as e:
            print(f"❌ Error detecting color signal: {e}")
            return None
    
    def get_spinner(self) -> str:
        """Get next spinner character"""
        char = self.spinner_chars[self.spinner_index]
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        return char
    
    # Copy EXACT working signing logic from ultimate_scalping_bot.py and order_book_hunter.py
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
        return self.sign_inner(data)
    
    async def place_order_raw(self, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Place order using raw API call"""
        try:
            # Get nonce
            nonce = int(time.time() * 1000)
            vault = None
            is_mainnet = True
            
            # Sign the action using the EXACT working method
            signature = self.sign_action(action, vault, nonce, is_mainnet)
            
            # Prepare the request payload
            payload = {
                "action": action,
                "nonce": nonce,
                "signature": signature,
                "vaultAddress": vault
            }
            
            # Make the request
            url = "https://api.hyperliquid.xyz/exchange"
            headers = {"Content-Type": "application/json"}
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                print(f"❌ Order failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error placing order: {e}")
            return None
    
    async def enter_position(self, direction: str, entry_price: float) -> bool:
        """Enter a position (long or short)"""
        try:
            print(f"\n🚀 ENTERING {direction.upper()} POSITION")
            print(f"   Entry Price: ${entry_price:.2f}")
            
            # Calculate position size in SOL
            position_size_sol = round(self.position_usd / entry_price, 2)
            position_size_sol = max(0.01, position_size_sol)  # Minimum 0.01 SOL
            
            print(f"   Position Size: {position_size_sol} SOL (${self.position_usd:,.0f})")
            print(f"   Leverage: {self.leverage}x")
            print(f"   Your Capital: ${self.actual_capital:.0f}")
            
            # Determine order side and price
            is_buy = direction.lower() == "long"
            
            # Use IOC limit order with wide spread to ensure fill
            if is_buy:
                order_price = round(entry_price * 1.01, 2)  # 1% above market for buy
            else:
                order_price = round(entry_price * 0.99, 2)  # 1% below market for sell
            
            # Create order action
            order_action = {
                "type": "order",
                "orders": [{
                    "a": 5,  # SOL asset ID
                    "b": is_buy,
                    "p": self.round_float(order_price, 2),
                    "s": self.round_float(position_size_sol, 2),
                    "r": False,  # Not reduce only
                    "t": {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
                }],
                "grouping": "na"
            }
            
            # Place the order
            result = await self.place_order_raw(order_action)
            
            if result and 'response' in result and 'data' in result['response']:
                statuses = result['response']['data']['statuses']
                
                for status in statuses:
                    if 'filled' in status:
                        filled_data = status['filled']
                        print(f"✅ Position opened successfully!")
                        print(f"   Order ID: {filled_data.get('oid', 'N/A')}")
                        print(f"   Filled Size: {filled_data.get('totalSz', 'N/A')} SOL")
                        print(f"   Avg Price: ${float(filled_data.get('avgPx', 0)):.2f}")
                        
                        # Store position data
                        self.entry_order_data = filled_data
                        self.position_size = float(filled_data.get('totalSz', 0))
                        self.position_direction = direction.lower()
                        self.position_open = True
                        self.current_position = direction.lower()
                        
                        return True
                
                print(f"❌ Order not filled: {statuses}")
                return False
            else:
                print(f"❌ Failed to place order: {result}")
                return False
                
        except Exception as e:
            print(f"❌ Error entering position: {e}")
            return False
    
    async def close_position(self) -> bool:
        """Close current position using stored order data"""
        try:
            if not self.position_open:
                print("❌ No position to close")
                return True
            
            print(f"\n🔄 CLOSING {self.position_direction.upper()} POSITION")
            print(f"   Wallet: {self.address}")  # Debug wallet address
            
            # Get current price
            current_price = self.get_current_price()
            if current_price is None:
                print("❌ Cannot get current price")
                return False
            
            # If we don't have position size from order data, estimate it
            if not self.position_size:
                self.position_size = round(self.position_usd / current_price, 2)
                print(f"⚠️  No stored position size, estimating: {self.position_size} SOL")
            
            # Determine close direction (opposite of entry)
            close_direction = "SELL" if self.position_direction == "long" else "BUY"
            is_buy = close_direction == "BUY"
            
            # Calculate close price with wide spread to ensure fill
            if is_buy:
                close_price = round(current_price * 1.01, 2)  # 1% above for buy
            else:
                close_price = round(current_price * 0.99, 2)  # 1% below for sell
            
            print(f"   Close Direction: {close_direction}")
            print(f"   Close Price: ${close_price:.2f}")
            print(f"   Close Size: {self.position_size}")
            
            # Create close order action
            close_action = {
                "type": "order",
                "orders": [{
                    "a": 5,  # SOL asset ID
                    "b": is_buy,
                    "p": self.round_float(close_price, 2),
                    "s": self.round_float(self.position_size, 2),
                    "r": True,  # Reduce only
                    "t": {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
                }],
                "grouping": "na"
            }
            
            # Place close order
            result = await self.place_order_raw(close_action)
            
            if result and 'response' in result and 'data' in result['response']:
                statuses = result['response']['data']['statuses']
                
                for status in statuses:
                    if 'filled' in status:
                        filled_data = status['filled']
                        print(f"✅ Position closed successfully!")
                        print(f"   Filled Size: {filled_data.get('totalSz', 'N/A')} SOL")
                        print(f"   Avg Price: ${float(filled_data.get('avgPx', 0)):.2f}")
                        
                        # Reset position state
                        self.entry_order_data = None
                        self.position_size = None
                        self.position_direction = None
                        self.position_open = False
                        self.current_position = None
                        
                        return True
                
                print(f"❌ Close order not filled: {statuses}")
                return False
            else:
                print(f"❌ Failed to close position: {result}")
                return False
                
        except Exception as e:
            print(f"❌ Error closing position: {e}")
            return False
        finally:
            # Always reset position state on error
            if not self.position_open:
                self.entry_order_data = None
                self.position_size = None
                self.position_direction = None
                self.current_position = None
    
    async def flip_position(self, new_direction: str):
        """Flip position from current to new direction"""
        current_price = self.get_current_price()
        if current_price is None:
            print("❌ Cannot get current price for position flip")
            return False
        
        print(f"\n🔄 FLIPPING POSITION: {self.current_position} → {new_direction}")
        print(f"   Current Price: ${current_price:.2f}")
        
        try:
            # Step 1: Close current position if exists
            if self.position_open and self.entry_order_data:
                print("🔄 Closing current position...")
                close_success = await self.close_position()
                if not close_success:
                    print("❌ Failed to close current position")
                    return False
                
                # Wait 10 seconds for margin to be released
                print("⏳ Waiting 10 seconds for margin to be released...")
                await asyncio.sleep(10.0)
            
            # Step 2: Open new position
            print(f"🚀 Opening new {new_direction.upper()} position...")
            open_success = await self.enter_position(new_direction, current_price)
            
            if open_success:
                self.current_position = new_direction
                print(f"✅ Position flipped successfully to {new_direction.upper()}!")
                return True
            else:
                print(f"❌ Failed to open new {new_direction} position")
                return False
                
        except Exception as e:
            print(f"❌ Error flipping position: {e}")
            return False
    
    async def run(self):
        """Main trading loop"""
        try:
            print("\n🎨 EXPERIMENTAL COLOR TRADER STARTING!")
            print("=" * 60)
            print(f"💰 Strategy: Screen Color Detection Trading")
            print(f"📊 Position: ${self.position_usd:,.0f} with {self.leverage}x leverage")
            print(f"💵 Your Capital: ${self.actual_capital:.0f}")
            print(f"🎯 Signals: 🟢 GREEN = LONG | 🔴 RED = SHORT")
            print("=" * 60)
            
            # Calibrate screen region
            self.calibrate_screen_region()
            
            print("\n🚀 STARTING COLOR DETECTION TRADING...")
            print("Press Ctrl+C to stop")
            print()
            
            last_color_display = 0
            
            while True:
                current_time = time.time()
                
                # Capture screen and detect color
                if current_time - self.last_signal_time >= self.signal_cooldown:
                    try:
                        # Capture screen region
                        image = self.capture_screen_region()
                        if image is not None:
                            # Get dominant color
                            dominant_color = self.get_dominant_color(image)
                            
                            # Detect signal
                            signal = self.detect_color_signal(dominant_color)
                            
                            # Display color info every 5 seconds
                            if current_time - last_color_display >= 5.0:
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                spinner = self.get_spinner()
                                
                                # Format color display
                                color_str = f"RGB{dominant_color}"
                                signal_str = "🟢 LONG" if signal == "LONG" else "🔴 SHORT" if signal == "SHORT" else "⚪ NEUTRAL"
                                position_str = f"📍 {self.current_position.upper()}" if self.current_position else "📍 NO POSITION"
                                
                                print(f"{spinner} [{timestamp}] Color: {color_str} | Signal: {signal_str} | {position_str}")
                                last_color_display = current_time
                            
                            # Handle signal changes
                            if signal and signal != self.current_signal:
                                print(f"\n🚨 COLOR SIGNAL DETECTED: {signal}!")
                                print(f"   Dominant Color: RGB{dominant_color}")
                                
                                # Check if we need to flip position
                                if signal.lower() != self.current_position:
                                    print(f"   Position Change Required: {self.current_position} → {signal.lower()}")
                                    
                                    # Flip position
                                    success = await self.flip_position(signal.lower())
                                    if success:
                                        print(f"✅ Successfully flipped to {signal}!")
                                    else:
                                        print(f"❌ Failed to flip to {signal}")
                                
                                self.current_signal = signal
                                self.last_signal_time = current_time
                        
                    except Exception as e:
                        print(f"❌ Error in color detection: {e}")
                
                # Small delay to prevent excessive CPU usage
                await asyncio.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down Color Trader...")
            
            # Close any open positions
            if self.position_open:
                print("🔄 Closing position on shutdown...")
                await self.close_position()
            
            print("👋 Goodbye!")
            
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            
            # Close any open positions on error
            if self.position_open:
                print("🔄 Closing position due to error...")
                try:
                    await self.close_position()
                except:
                    pass

if __name__ == "__main__":
    bot = ExperimentalColorTrader()
    asyncio.run(bot.run())
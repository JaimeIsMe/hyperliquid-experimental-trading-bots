#!/usr/bin/env python3
"""
🎨 Color Trader Web Server
FastAPI backend for the Experimental Color Trader with real-time WebSocket updates
"""

import asyncio
import json
import base64
import io
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import pyautogui
from PIL import Image
import numpy as np
from experimental_color_trader import ExperimentalColorTrader
import threading
import time

# Disable pyautogui failsafe for server environment
pyautogui.FAILSAFE = False

app = FastAPI(title="Color Trader Web Interface", version="1.0.0")

# Global state
bot_instance: Optional[ExperimentalColorTrader] = None
bot_thread: Optional[threading.Thread] = None
bot_running = False
connected_clients: List[WebSocket] = []
current_status = {
    "bot_running": False,
    "position_open": False,
    "position_direction": None,
    "position_size": 0,
    "current_price": 0,
    "detected_color": [0, 0, 0],
    "signal": None,
    "screen_region": {"x": 100, "y": 100, "width": 200, "height": 200},
    "last_trade": None,
    "pnl": 0
}

# Pydantic models
class ScreenRegion(BaseModel):
    x: int
    y: int
    width: int
    height: int

class ColorSettings(BaseModel):
    green_target: List[int]
    red_target: List[int]
    color_tolerance: int

class BotSettings(BaseModel):
    screen_region: ScreenRegion
    color_settings: ColorSettings
    position_size_usd: float
    leverage: int
    tp_percentage: float
    sl_percentage: float

class TradeRecord(BaseModel):
    timestamp: str
    action: str
    direction: str
    price: float
    size: float
    color: List[int]

# Store trade history
trade_history: List[TradeRecord] = []

@app.get("/")
async def get_dashboard():
    """Serve the main dashboard HTML"""
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎨 Color Trader Dashboard</title>
    <script src="https://unpkg.com/react@18/umd/react.development.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .color-preview {
            transition: all 0.3s ease;
            box-shadow: 0 0 20px rgba(0,0,0,0.3);
        }
        .signal-indicator {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .trade-entry {
            animation: slideIn 0.5s ease-out;
        }
        @keyframes slideIn {
            from { transform: translateY(-20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
    </style>
</head>
<body class="bg-gray-900 text-white">
    <div id="root"></div>
    
    <script type="text/babel">
        const { useState, useEffect, useRef } = React;
        
        function ColorTraderDashboard() {
            const [status, setStatus] = useState({
                bot_running: false,
                position_open: false,
                position_direction: null,
                detected_color: [0, 0, 0],
                signal: null,
                current_price: 0,
                pnl: 0
            });
            const [screenCapture, setScreenCapture] = useState(null);
            const [tradeHistory, setTradeHistory] = useState([]);
            const [settings, setSettings] = useState({
                screen_region: { x: 100, y: 100, width: 200, height: 200 },
                color_settings: {
                    green_target: [76, 175, 80],
                    red_target: [241, 147, 65],
                    color_tolerance: 80
                },
                position_size_usd: 300,
                leverage: 40,
                tp_percentage: 0.31,
                sl_percentage: 0.125
            });
            
            const wsRef = useRef(null);
            
            useEffect(() => {
                // Connect to WebSocket
                const ws = new WebSocket('ws://localhost:8000/ws');
                wsRef.current = ws;
                
                ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'status_update') {
                        setStatus(data.data);
                    } else if (data.type === 'screen_capture') {
                        setScreenCapture(data.data);
                    } else if (data.type === 'trade_history') {
                        setTradeHistory(data.data);
                    }
                };
                
                ws.onopen = () => {
                    console.log('Connected to Color Trader WebSocket');
                };
                
                ws.onclose = () => {
                    console.log('Disconnected from WebSocket');
                };
                
                return () => {
                    ws.close();
                };
            }, []);
            
            const startBot = async () => {
                try {
                    const response = await fetch('/api/start-bot', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(settings)
                    });
                    if (!response.ok) throw new Error('Failed to start bot');
                } catch (error) {
                    alert('Error starting bot: ' + error.message);
                }
            };
            
            const stopBot = async () => {
                try {
                    const response = await fetch('/api/stop-bot', { method: 'POST' });
                    if (!response.ok) throw new Error('Failed to stop bot');
                } catch (error) {
                    alert('Error stopping bot: ' + error.message);
                }
            };
            
            const captureScreen = async () => {
                try {
                    const response = await fetch('/api/capture-screen', { method: 'POST' });
                    if (!response.ok) throw new Error('Failed to capture screen');
                } catch (error) {
                    console.error('Error capturing screen:', error);
                }
            };
            
            const colorToRgb = (color) => `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
            
            return (
                <div className="min-h-screen p-6">
                    <div className="max-w-7xl mx-auto">
                        {/* Header */}
                        <div className="mb-8 text-center">
                            <h1 className="text-4xl font-bold mb-2">🎨 Color Trader Dashboard</h1>
                            <p className="text-gray-400">Real-time visual signal detection for Hyperliquid trading</p>
                        </div>
                        
                        {/* Main Controls */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                            {/* Bot Status */}
                            <div className="bg-gray-800 rounded-lg p-6">
                                <h2 className="text-xl font-semibold mb-4">🤖 Bot Status</h2>
                                <div className="space-y-3">
                                    <div className="flex justify-between items-center">
                                        <span>Status:</span>
                                        <span className={`px-3 py-1 rounded-full text-sm ${
                                            status.bot_running ? 'bg-green-600' : 'bg-red-600'
                                        }`}>
                                            {status.bot_running ? '🟢 Running' : '🔴 Stopped'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span>Position:</span>
                                        <span className={`px-3 py-1 rounded-full text-sm ${
                                            status.position_open 
                                                ? (status.position_direction === 'long' ? 'bg-green-600' : 'bg-red-600')
                                                : 'bg-gray-600'
                                        }`}>
                                            {status.position_open 
                                                ? `📈 ${status.position_direction?.toUpperCase()}`
                                                : '💤 None'
                                            }
                                        </span>
                                    </div>
                                    <div className="flex justify-between items-center">
                                        <span>P&L:</span>
                                        <span className={`font-mono ${status.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                            ${status.pnl.toFixed(2)}
                                        </span>
                                    </div>
                                </div>
                                
                                <div className="mt-6 space-y-3">
                                    {!status.bot_running ? (
                                        <button 
                                            onClick={startBot}
                                            className="w-full bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg font-semibold transition-colors"
                                        >
                                            🚀 Start Bot
                                        </button>
                                    ) : (
                                        <button 
                                            onClick={stopBot}
                                            className="w-full bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg font-semibold transition-colors"
                                        >
                                            ⏹️ Stop Bot
                                        </button>
                                    )}
                                    <button 
                                        onClick={captureScreen}
                                        className="w-full bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg font-semibold transition-colors"
                                    >
                                        📸 Capture Screen
                                    </button>
                                </div>
                            </div>
                            
                            {/* Color Detection */}
                            <div className="bg-gray-800 rounded-lg p-6">
                                <h2 className="text-xl font-semibold mb-4">🎨 Color Detection</h2>
                                <div className="space-y-4">
                                    <div className="text-center">
                                        <div 
                                            className="color-preview w-24 h-24 mx-auto rounded-lg mb-3"
                                            style={{ backgroundColor: colorToRgb(status.detected_color) }}
                                        ></div>
                                        <p className="text-sm text-gray-400">Detected Color</p>
                                        <p className="font-mono text-sm">
                                            RGB({status.detected_color[0]}, {status.detected_color[1]}, {status.detected_color[2]})
                                        </p>
                                    </div>
                                    
                                    {status.signal && (
                                        <div className={`signal-indicator text-center p-3 rounded-lg ${
                                            status.signal === 'long' ? 'bg-green-600' : 'bg-red-600'
                                        }`}>
                                            <div className="text-2xl mb-1">
                                                {status.signal === 'long' ? '📈' : '📉'}
                                            </div>
                                            <div className="font-semibold">
                                                {status.signal === 'long' ? 'LONG SIGNAL' : 'SHORT SIGNAL'}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                            
                            {/* Screen Capture */}
                            <div className="bg-gray-800 rounded-lg p-6">
                                <h2 className="text-xl font-semibold mb-4">📺 Screen Capture</h2>
                                <div className="text-center">
                                    {screenCapture ? (
                                        <img 
                                            src={`data:image/png;base64,${screenCapture}`}
                                            alt="Screen capture"
                                            className="max-w-full h-32 object-contain mx-auto rounded-lg border border-gray-600"
                                        />
                                    ) : (
                                        <div className="h-32 bg-gray-700 rounded-lg flex items-center justify-center">
                                            <span className="text-gray-400">No capture yet</span>
                                        </div>
                                    )}
                                    <p className="text-xs text-gray-400 mt-2">
                                        Region: {settings.screen_region.x}, {settings.screen_region.y} 
                                        ({settings.screen_region.width}×{settings.screen_region.height})
                                    </p>
                                </div>
                            </div>
                        </div>
                        
                        {/* Trade History */}
                        <div className="bg-gray-800 rounded-lg p-6">
                            <h2 className="text-xl font-semibold mb-4">📊 Trade History</h2>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-gray-700">
                                            <th className="text-left py-2">Time</th>
                                            <th className="text-left py-2">Action</th>
                                            <th className="text-left py-2">Direction</th>
                                            <th className="text-left py-2">Price</th>
                                            <th className="text-left py-2">Size</th>
                                            <th className="text-left py-2">Color</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {tradeHistory.slice(-10).reverse().map((trade, index) => (
                                            <tr key={index} className="trade-entry border-b border-gray-700">
                                                <td className="py-2 font-mono text-xs">{trade.timestamp}</td>
                                                <td className="py-2">
                                                    <span className={`px-2 py-1 rounded text-xs ${
                                                        trade.action === 'OPEN' ? 'bg-green-600' : 'bg-red-600'
                                                    }`}>
                                                        {trade.action}
                                                    </span>
                                                </td>
                                                <td className="py-2">
                                                    <span className={`px-2 py-1 rounded text-xs ${
                                                        trade.direction === 'long' ? 'bg-blue-600' : 'bg-orange-600'
                                                    }`}>
                                                        {trade.direction?.toUpperCase()}
                                                    </span>
                                                </td>
                                                <td className="py-2 font-mono">${trade.price}</td>
                                                <td className="py-2 font-mono">{trade.size}</td>
                                                <td className="py-2">
                                                    <div 
                                                        className="w-6 h-6 rounded border border-gray-600"
                                                        style={{ backgroundColor: colorToRgb(trade.color) }}
                                                    ></div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                                {tradeHistory.length === 0 && (
                                    <div className="text-center py-8 text-gray-400">
                                        No trades yet. Start the bot to begin trading!
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            );
        }
        
        ReactDOM.render(<ColorTraderDashboard />, document.getElementById('root'));
    </script>
</body>
</html>
    """)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    connected_clients.append(websocket)
    
    try:
        # Send initial status
        await websocket.send_text(json.dumps({
            "type": "status_update",
            "data": current_status
        }))
        
        # Send trade history
        await websocket.send_text(json.dumps({
            "type": "trade_history", 
            "data": trade_history
        }))
        
        # Keep connection alive
        while True:
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def broadcast_update(update_type: str, data: dict):
    """Broadcast updates to all connected clients"""
    if connected_clients:
        message = json.dumps({"type": update_type, "data": data})
        disconnected = []
        
        for client in connected_clients:
            try:
                await client.send_text(message)
            except:
                disconnected.append(client)
        
        # Remove disconnected clients
        for client in disconnected:
            connected_clients.remove(client)

@app.post("/api/start-bot")
async def start_bot(settings: BotSettings):
    """Start the color trading bot"""
    global bot_instance, bot_thread, bot_running
    
    if bot_running:
        raise HTTPException(status_code=400, detail="Bot is already running")
    
    try:
        # Create bot instance with settings
        bot_instance = ExperimentalColorTrader()
        
        # Apply settings
        bot_instance.screen_region = (
            settings.screen_region.x,
            settings.screen_region.y, 
            settings.screen_region.width,
            settings.screen_region.height
        )
        bot_instance.green_target = tuple(settings.color_settings.green_target)
        bot_instance.red_target = tuple(settings.color_settings.red_target)
        bot_instance.color_tolerance = settings.color_settings.color_tolerance
        bot_instance.position_size_usd = settings.position_size_usd
        bot_instance.leverage = settings.leverage
        bot_instance.tp_percentage = settings.tp_percentage
        bot_instance.sl_percentage = settings.sl_percentage
        
        # Start bot in separate thread
        bot_running = True
        bot_thread = threading.Thread(target=run_bot_with_updates, daemon=True)
        bot_thread.start()
        
        current_status["bot_running"] = True
        await broadcast_update("status_update", current_status)
        
        return {"status": "Bot started successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {str(e)}")

@app.post("/api/stop-bot")
async def stop_bot():
    """Stop the color trading bot"""
    global bot_running, bot_instance
    
    bot_running = False
    if bot_instance:
        # Close any open positions
        try:
            if bot_instance.position_open:
                await asyncio.get_event_loop().run_in_executor(None, bot_instance.close_position)
        except:
            pass
    
    current_status["bot_running"] = False
    current_status["position_open"] = False
    await broadcast_update("status_update", current_status)
    
    return {"status": "Bot stopped successfully"}

@app.post("/api/capture-screen")
async def capture_screen():
    """Capture current screen region and return as base64"""
    try:
        region = current_status["screen_region"]
        screenshot = pyautogui.screenshot(region=(
            region["x"], region["y"], region["width"], region["height"]
        ))
        
        # Convert to base64
        buffer = io.BytesIO()
        screenshot.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        await broadcast_update("screen_capture", img_base64)
        
        return {"status": "Screen captured successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture screen: {str(e)}")

def run_bot_with_updates():
    """Run the bot with periodic status updates"""
    global current_status, trade_history
    
    while bot_running and bot_instance:
        try:
            # Get current screen capture and analyze color
            region = bot_instance.screen_region
            screenshot = pyautogui.screenshot(region=region)
            
            # Get dominant color
            dominant_color = bot_instance.get_dominant_color(screenshot)
            current_status["detected_color"] = list(dominant_color)
            
            # Get signal
            signal = bot_instance.get_signal_from_color(dominant_color)
            current_status["signal"] = signal
            
            # Update position status
            current_status["position_open"] = bot_instance.position_open
            current_status["position_direction"] = bot_instance.position_direction
            
            # Get current price
            try:
                price_data = bot_instance.info.all_mids()
                if price_data and len(price_data) > bot_instance.asset_index:
                    current_status["current_price"] = float(price_data[bot_instance.asset_index])
            except:
                pass
            
            # Process trading logic
            if signal and signal != bot_instance.position_direction:
                # Record trade
                trade_record = TradeRecord(
                    timestamp=datetime.now().strftime("%H:%M:%S"),
                    action="FLIP" if bot_instance.position_open else "OPEN",
                    direction=signal,
                    price=current_status["current_price"],
                    size=bot_instance.position_size_usd / bot_instance.leverage,
                    color=list(dominant_color)
                )
                trade_history.append(trade_record)
                
                # Execute trade (simplified - in real implementation, call bot methods)
                print(f"🎨 Signal detected: {signal} from color {dominant_color}")
                
                # Update position
                bot_instance.position_direction = signal
                bot_instance.position_open = True
            
            # Broadcast updates
            asyncio.run(broadcast_update("status_update", current_status))
            asyncio.run(broadcast_update("trade_history", [t.dict() for t in trade_history]))
            
            # Convert screenshot to base64 for streaming
            buffer = io.BytesIO()
            screenshot.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            asyncio.run(broadcast_update("screen_capture", img_base64))
            
        except Exception as e:
            print(f"Error in bot loop: {e}")
        
        time.sleep(1)  # Update every second

if __name__ == "__main__":
    import uvicorn
    print("🎨 Starting Color Trader Web Server...")
    print("🌐 Dashboard will be available at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
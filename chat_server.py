#!/usr/bin/env python3

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import socket
import threading
import websockets
import sqlite3
import signal
import sys
from datetime import datetime
import pe
import pe.app
import zlib
import json
import base64
import configparser

CONFIG_FILE = 'chat_server.conf'

def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        config['DEFAULT'] = {
            'SRC_CALLSIGN': 'N0CALL',
            'DEST_CALLSIGN': 'APRS',
            'WEBSOCKET_HOST': '0.0.0.0',
            'WEBSOCKET_PORT': '6789',
            'HTTP_PORT': '8080',
            'AGW_SERVER': socket.gethostname(),
            'AGW_PORT': '8000',
            'DB_NAME': 'chat_messages.db',
            'TABLE_NAME': 'messages',
            'MAX_ROWS': '100',
            'WEB_CLIENT_NAME': 'web_client.html',
            'USE_COMPRESSION': 'true'
        }
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Config file '{CONFIG_FILE}' created. Please edit it before running the server.")
        sys.exit(1)
    config.read(CONFIG_FILE)
    return config['DEFAULT']

config = load_config()
SRC_CALLSIGN = config.get('SRC_CALLSIGN', 'N0CALL')
WEBSOCKET_HOST = config.get('WEBSOCKET_HOST', '0.0.0.0')
WEBSOCKET_PORT = int(config.get('WEBSOCKET_PORT', 6789))
HTTP_PORT = int(config.get('HTTP_PORT', 8080))
AGW_SERVER = config.get('AGW_SERVER', socket.gethostname())
AGW_PORT = int(config.get('AGW_PORT', 8000))
DB_NAME = config.get('DB_NAME', 'chat_messages.db')
TABLE_NAME = config.get('TABLE_NAME', 'messages')
MAX_ROWS = int(config.get('MAX_ROWS', 100))
DEST_CALLSIGN = config.get('DEST_CALLSIGN', 'APRS')
WEB_CLIENT_NAME = config.get('WEB_CLIENT_NAME', 'web_client.html')
USE_COMPRESSION = bool(config.get('USE_COMPRESSION', 'TRUE'))
WEB_CLIENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), WEB_CLIENT_NAME)

class SingleFileHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            config_data = json.dumps({"host": WEBSOCKET_HOST, "port": WEBSOCKET_PORT})
            self.wfile.write(config_data.encode())
            return
        
        try:
            with open(WEB_CLIENT, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")


class HTTPServerThread(threading.Thread):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.httpd = HTTPServer(('0.0.0.0', self.port), SingleFileHTTPRequestHandler)

    def run(self):
        print(f"Serving web_client.html on port {self.port}")
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        print("HTTP server stopped")

class APRSReceiveHandler(pe.ReceiveHandler):
    def __init__(self, irc_server):
        self.irc_server = irc_server
        self.loop = asyncio.get_event_loop()

    def monitored_own(self, port, call_from, call_to, text, data):
        message = self.extract_text_from_bytearray(data)
        self.loop.create_task(self.handle_aprs_message(call_from, message))

    def monitored_unproto(self, port, call_from, call_to, text, data):
        message = self.extract_text_from_bytearray(data)
        self.loop.create_task(self.handle_aprs_message(call_from, message))

    def extract_text_from_bytearray(self, data: bytearray) -> str:
        if self.irc_server.use_compression:
            try:
                return zlib.decompress(base64.b64decode(data)).decode('utf-8')
            except Exception:
                return data.decode('utf-8', errors='ignore')
        else:
            return data.decode('utf-8', errors='ignore')

    async def handle_aprs_message(self, call_from, aprs_message):
        try:
            aprs_data = json.loads(aprs_message)
            timestamp = aprs_data.get('timestamp', datetime.now().strftime('%m/%d/%y %H:%M'))
            username = aprs_data.get('username', 'unknown')
            message = aprs_data.get('message', '')
        except json.JSONDecodeError:
            timestamp = datetime.now().strftime('%m/%d/%y %H:%M')
            username = call_from
            message = aprs_message

        message_dict = {'timestamp': timestamp, 'username': username, 'message': message}
        self.irc_server.store_message(timestamp, username, message)
        await self.irc_server.broadcast_aprs_message(json.dumps(message_dict))

class ChatServer:
    def __init__(self, host, port, agw_server, agw_port, src_callsign, use_compression):
        self.host = host
        self.port = port
        self.agw_server = agw_server
        self.agw_port = agw_port
        self.src_callsign = src_callsign
        self.use_compression = use_compression
        self.clients = {}
        self.http_server_thread = HTTPServerThread(HTTP_PORT)
        self.http_server_thread.start()
        self.init_db()
        self.init_aprs()
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

    def init_db(self):
        self.conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL             
            )
        ''')
        self.conn.commit()

    def init_aprs(self):
        self.aprs_app = pe.app.Application()
        self.aprs_app.use_custom_handler(APRSReceiveHandler(self))
        self.aprs_app.start(self.agw_server, self.agw_port)
        self.aprs_app.enable_monitoring = True

    async def handle_client(self, websocket):
        try:
            await websocket.send("Enter your username: ")
            username = await websocket.recv()
            username = username.strip()
            self.clients[websocket] = username
            await websocket.send(f"Welcome, {username}!")
            await self.send_all_messages(websocket)
            async for message in websocket:
                await self.broadcast(message, websocket)
        except websockets.ConnectionClosed:
            await self.remove_client(websocket)

    async def broadcast(self, message, websocket):
        timestamp = datetime.now().strftime('%m/%d/%y %H:%M')
        username = self.clients.get(websocket, "unknown")
        message_dict = {'timestamp': timestamp, 'username': username, 'message': message}
        await self.broadcast_aprs_message(json.dumps(message_dict))

    async def broadcast_aprs_message(self, message):
        for client in list(self.clients.keys()):
            try:
                await client.send(message)
            except Exception:
                await self.remove_client(client)

    async def send_all_messages(self, websocket):
        self.cursor.execute(f'SELECT timestamp, username, message FROM {TABLE_NAME} ORDER BY id')
        messages = self.cursor.fetchall()
        for timestamp, username, message in messages:
            await websocket.send(json.dumps({'timestamp': timestamp, 'username': username, 'message': message}))

    async def remove_client(self, websocket):
        if websocket in self.clients:
            del self.clients[websocket]
        await websocket.close()

    async def start(self):
        self.server = await websockets.serve(self.handle_client, self.host, self.port)
        print(f"Server started on {self.host}:{self.port}")
        await self.server.wait_closed()

    def cleanup(self, signum, frame):
        print("Shutting down server...")

        for client in list(self.clients.keys()):
            asyncio.create_task(client.close())

        self.conn.close()
        self.aprs_app.stop()
        self.http_server_thread.stop()

        loop = asyncio.get_running_loop()

        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        loop.stop()
        sys.exit(0)

if __name__ == "__main__":
    server = ChatServer(WEBSOCKET_HOST, WEBSOCKET_PORT, AGW_SERVER, AGW_PORT, SRC_CALLSIGN, USE_COMPRESSION)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        server.cleanup(None, None)
    finally:
        loop.run_until_complete(asyncio.sleep(0))  # Ensure all cleanup tasks complete
        loop.close()
        sys.exit(0)  # Force exit
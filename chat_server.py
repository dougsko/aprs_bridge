#!/usr/bin/env python3

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
HOSTNAME = socket.gethostname()

def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_FILE):
        config['DEFAULT'] = {
            'SRC_CALLSIGN': 'N0CALL',
            'DEST_CALLSIGN': 'APRS',
            'HOSTNAME': HOSTNAME,
            'WEBSOCKET_HOST': '0.0.0.0',
            'WEBSOCKET_PORT': '6789',
            'HTTP_PORT': '8080',
            'AGW_SERVER': HOSTNAME,
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
DEST_CALLSIGN = config.get('DEST_CALLSIGN', 'APRS')
HOSTNAME = config.get('HOSTNAME')
WEBSOCKET_LISTEN_ADDRESS = config.get('WEBSOCKET_LISTEN_ADDRESS', '0.0.0.0')
WEBSOCKET_PORT = int(config.get('WEBSOCKET_PORT', 6789))
HTTP_PORT = int(config.get('HTTP_PORT', 8080))
AGW_SERVER = config.get('AGW_SERVER', HOSTNAME)
AGW_PORT = int(config.get('AGW_PORT', 8000))
DB_NAME = config.get('DB_NAME', 'chat_messages.db')
TABLE_NAME = config.get('TABLE_NAME', 'messages')
MAX_ROWS = int(config.get('MAX_ROWS', 100))
DEST_CALLSIGN = config.get('DEST_CALLSIGN', 'APRS')
WEB_CLIENT_NAME = config.get('WEB_CLIENT_NAME', 'web_client.html')
USE_COMPRESSION = bool(config.get('USE_COMPRESSION', 'TRUE'))
WEB_CLIENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), WEB_CLIENT_NAME)

class APRSReceiveHandler(pe.ReceiveHandler):
    def __init__(self, irc_server):
        self.irc_server = irc_server
        self.loop = asyncio.get_event_loop()

    def monitored_own(self, port, call_from, call_to, text, data):
        message = self.extract_text_from_bytearray(data)
        print(f"APRS message received: {message}")
        self.loop.run_until_complete(self.handle_aprs_message(call_from, message))

    def monitored_unproto(self, port, call_from, call_to, text, data):
        print(f"INSIDE MONITORED UNPROTO")
        message = self.extract_text_from_bytearray(data)
        print(f"APRS message received from {call_from}: {message}")
        self.loop.run_until_complete(self.handle_aprs_message(call_from, message))

    def extract_text_from_bytearray(self, data: bytearray) -> str:
        if self.irc_server.use_compression:
            try:
                print(f"Attempting to decompress message: {data}")
                return zlib.decompress(base64.b64decode(data)).decode('utf-8')
            except Exception:
                return data.decode('utf-8', errors='ignore')
        else:
            return data.decode('utf-8', errors='ignore')

    async def handle_aprs_message(self, call_from, aprs_message):
        print("inside handle_aprs_message")
        print(f"aprs_message is {aprs_message}")
        try:
            aprs_data = json.loads(aprs_message)
            timestamp = aprs_data.get('timestamp', datetime.now().strftime('%m/%d/%y %H:%M'))
            username = aprs_data.get('username', 'unknown')
            message = aprs_data.get('message', '')
        except json.JSONDecodeError:
            print("Error decoding APRS message JSON")
            timestamp = datetime.now().strftime('%m/%d/%y %H:%M')
            username = call_from
            message = aprs_message

        message_dict = {
            'timestamp': timestamp,
            'username': username,
            'message': message
        }
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
        print(f"Connected to AGW server at {self.agw_server}:{self.agw_port}")

    async def broadcast(self, message, websocket):
        timestamp = datetime.now().strftime('%m/%d/%y %H:%M')
        username = self.clients[websocket]
        
        message_dict = {
            'timestamp': timestamp,
            'username': username,
            'message': message
        }

        message_json = json.dumps(message_dict)

        self.send_aprs_message(message_json)

    def send_aprs_message(self, message):
        message = self.create_aprs_message(message)
        self.aprs_app.send_unproto(0, self.src_callsign, DEST_CALLSIGN, message, ['WIDE1-1'])

    def create_aprs_message(self, message: str) -> bytearray:
        encoded_message = message.encode('utf-8')
        if self.use_compression:
            return base64.b64encode(zlib.compress(encoded_message))
        return bytearray(encoded_message)

    async def broadcast_aprs_message(self, message):
        if not self.clients:
            print("No clients connected to send APRS messages to.")
            return

        print(f"Starting to broadcast APRS message: {message}")
        clients_to_remove = []
        for client in self.clients:
            try:
                print(f"Sending APRS message to client: {self.clients[client]}")
                await client.send(message)
                print(f"APRS message sent to {self.clients[client]}")
            except Exception as e:
                print(f"Failed to send message to {self.clients[client]}: {e}")
                clients_to_remove.append(client)
        for client in clients_to_remove:
            await self.remove_client(client)

    def store_message(self, timestamp, username, message):
        self.cursor.execute(f'INSERT INTO {TABLE_NAME} (timestamp, username, message) VALUES (?, ?, ?)', (timestamp, username, message))
        self.conn.commit()
        self.cursor.execute(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        count = self.cursor.fetchone()[0]
        if count > MAX_ROWS:
            self.cursor.execute(f'DELETE FROM {TABLE_NAME} WHERE id IN (SELECT id FROM {TABLE_NAME} ORDER BY id LIMIT ?)', (count - MAX_ROWS,))
            self.conn.commit()

    async def send_all_messages(self, websocket):
        self.cursor.execute(f'SELECT timestamp, username, message FROM {TABLE_NAME} ORDER BY id')
        messages = self.cursor.fetchall()
        for timestamp, username, message in messages:
            message_dict = {
                'timestamp': timestamp,
                'username': username,
                'message': message
            }
            await websocket.send(json.dumps(message_dict))

    async def handle_client(self, websocket):
        try:
            while True:
                await websocket.send("Enter your username: ")
                username = await websocket.recv()
                username = username.strip()
                if username:
                    break
                await websocket.send("Username cannot be empty or spaces. Please enter a valid username.")

            self.clients[websocket] = username
            await websocket.send(f"Welcome, {username}!")
            await self.send_all_messages(websocket)
            async for message in websocket:
                await self.broadcast(message, websocket)
        except websockets.ConnectionClosed:
            await self.remove_client(websocket)
        except Exception as e:
            print(f"Error: {e}")
            await self.remove_client(websocket)

    async def remove_client(self, websocket):
        if websocket in self.clients:
            username = self.clients[websocket]
            print(f"Removing client: {username}")
            del self.clients[websocket]
            await websocket.close()

    async def start(self):
        server = await websockets.serve(self.handle_client, self.host, self.port)
        print(f"Websocket server started on {self.host}:{self.port}")
        await server.wait_closed()

    def cleanup(self, signum, frame):
        print(f"Shutting down websocket server..")
        for client in self.clients:
            asyncio.create_task(client.close())
        self.conn.close()
        self.aprs_app.stop()
        sys.exit(0)

# HTTP Server for serving web_client.html
class SingleFileHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == f"/{WEB_CLIENT_NAME}":
            try:
                with open(WEB_CLIENT, "rb") as f:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "File Not Found")
        else:
            self.send_error(403, "Forbidden")

def start_http_server():
    server_address = ("", HTTP_PORT)
    httpd = ThreadingHTTPServer(server_address, SingleFileHandler)
    print(f"HTTP server started on port {HTTP_PORT}, serving {WEB_CLIENT_NAME}")
    httpd.serve_forever()        


if __name__ == "__main__":
    server = ChatServer(WEBSOCKET_LISTEN_ADDRESS, WEBSOCKET_PORT, AGW_SERVER, AGW_PORT, SRC_CALLSIGN, USE_COMPRESSION)
    
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    asyncio.run(server.start())


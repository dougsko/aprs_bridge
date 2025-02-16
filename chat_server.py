#!/usr/bin/env python3

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
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
            'HOST': '0.0.0.0',
            'PORT': '6789',
            'HTTP_PORT': '8080',
            'DB_NAME': 'chat_messages.db',
            'TABLE_NAME': 'messages',
            'MAX_ROWS': '100',
            'DEST_CALLSIGN': 'APRS'
        }
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Config file '{CONFIG_FILE}' created. Please edit it before running the server.")
        sys.exit(1)
    config.read(CONFIG_FILE)
    return config['DEFAULT']

config = load_config()
HOST = config.get('HOST', '0.0.0.0')
PORT = int(config.get('PORT', 6789))
HTTP_PORT = int(config.get('HTTP_PORT', 8080))
DB_NAME = config.get('DB_NAME', 'chat_messages.db')
TABLE_NAME = config.get('TABLE_NAME', 'messages')
MAX_ROWS = int(config.get('MAX_ROWS', 100))
DEST_CALLSIGN = config.get('DEST_CALLSIGN', 'APRS')
WEB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_client.html")

class SingleFileHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with open(WEB_FILE, 'rb') as f:
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
    def __init__(self, use_compression):
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
        self.aprs_app.start(HOST, PORT)
        self.aprs_app.enable_monitoring = True

    async def start(self):
        self.server = await websockets.serve(self.handle_client, HOST, PORT)
        print(f"Server started on {HOST}:{PORT}")
        await self.server.wait_closed()

    def cleanup(self, signum, frame):
        print("Shutting down server...")
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
    server = ChatServer(use_compression=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        server.cleanup(None, None)
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
        sys.exit(0)

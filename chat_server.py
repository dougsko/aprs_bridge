#!/usr/bin/env python3

import argparse
import asyncio
import threading
import signal
import sys
import os
import websockets
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import pe
import pe.app
import zlib
import json
import base64

HOST = '0.0.0.0'
PORT = 6789
HTTP_PORT = 8080
DB_NAME = 'chat_messages.db'
TABLE_NAME = 'messages'
MAX_ROWS = 100
DEST_CALLSIGN = 'APRS'
WEB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_client.html")


class SingleFileHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve the web_client.html file regardless of the requested path."""
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
        super().__init__(daemon=True)
        self.port = port
        self.httpd = HTTPServer(('0.0.0.0', self.port), SingleFileHTTPRequestHandler)

    def run(self):
        print(f"Serving web_client.html on port {self.port}")
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        print("HTTP server stopped")


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
        self.server = None  # Placeholder for the WebSocket server

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
        self.aprs_app.start(self.agw_server, self.agw_port)
        self.aprs_app.enable_monitoring = True

    async def start(self):
        self.server = await websockets.serve(self.handle_client, self.host, self.port)
        print(f"Server started on {self.host}:{self.port}")
        await self.server.wait_closed()

    def cleanup(self, signum=None, frame=None):
        print("Shutting down server...")
        if self.server:
            asyncio.create_task(self.shutdown())

    async def shutdown(self):
        for client in list(self.clients.keys()):
            await client.close()
        self.conn.close()
        self.aprs_app.stop()
        self.http_server_thread.stop()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        print("Server shutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='WebSocket Chat Server with APRS integration.')
    parser.add_argument('--agw-server', type=str, default='orangepizero2w', help='APRS AGW server host (default: orangepizero2w)')
    parser.add_argument('--agw-port', type=int, default=8002, help='APRS AGW server port (default: 8002)')
    parser.add_argument('--src-callsign', type=str, default='K3DEP', help='Source callsign (default: K3DEP)')
    parser.add_argument('--use-compression', type=bool, default=True, help='Enable message compression (default: True)')

    args = parser.parse_args()
    server = ChatServer(HOST, PORT, args.agw_server, args.agw_port, args.src_callsign, args.use_compression)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        loop.run_until_complete(server.shutdown())
    finally:
        loop.close()

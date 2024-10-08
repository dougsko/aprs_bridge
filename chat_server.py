#!/usr/bin/env python3

import argparse
import asyncio
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

HOST = '0.0.0.0'
PORT = 6789
DB_NAME = 'chat_messages.db'
TABLE_NAME = 'messages'
MAX_ROWS = 100
DEST_CALLSIGN = 'APRS'


class APRSReceiveHandler(pe.ReceiveHandler):
    def __init__(self, irc_server):
        self.irc_server = irc_server
        self.loop = asyncio.get_event_loop()

    def monitored_own(self, port, call_from, call_to, text, data):
        message = self.extract_text_from_bytearray(data)
        print(f"APRS message received: {message}")
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

    async def handle_client(self, websocket, path):
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
        print(f"Server started on {self.host}:{self.port}")
        await server.wait_closed()

    def cleanup(self, signum, frame):
        print(f"Shutting down server...")
        for client in self.clients:
            asyncio.create_task(client.close())
        self.conn.close()
        self.aprs_app.stop()
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='WebSocket Chat Server with APRS integration.')
    parser.add_argument('--agw-server', type=str, default='orangepizero2w', help='APRS AGW server host (default: orangepizero2w)')
    parser.add_argument('--agw-port', type=int, default=8002, help='APRS AGW server port (default: 8002)')
    parser.add_argument('--src-callsign', type=str, default='K3DEP', help='Source callsign (default: K3DEP)')
    parser.add_argument('--use-compression', type=bool, default=True, help='Enable message compression (default: True)')
    
    args = parser.parse_args()

    server = ChatServer(HOST, PORT, args.agw_server, args.agw_port, args.src_callsign, args.use_compression)
    asyncio.run(server.start())

#!/usr/bin/env python3

import pe
import pe.app
import logging
import random
import string
import argparse
import asyncio
from nio import AsyncClient, RoomMessageText, LoginResponse, MatrixRoom, RoomMessage

# Function to create APRS message
def create_aprs_message(dest_callsign: str, message: str) -> bytearray:
    # padded_callsign = dest_callsign.ljust(9)[:9]
    # ack = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    aprs_message = f"{message}"
    return bytearray(aprs_message, 'utf-8')

# Function to extract text from bytearray
def extract_text_from_bytearray(data: bytearray) -> str:
    return data.decode('utf-8', errors='ignore')
    # text = data.decode('utf-8', errors='ignore')
    # start = text.find(':', text.find(':') + 1) + 1
    # end = text.find('{')
    # return text[start:end].strip() if start != -1 and end != -1 else text

# Configure logging for debugging
#logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('pe.handler')

# Custom receive handler for APRS messages
class MyReceiveHandler(pe.ReceiveHandler):
    def __init__(self, matrix_client, room_id):
        self.matrix_client = matrix_client
        self.room_id = room_id

    def monitored_own(self, port, call_from, call_to, text, data):
        aprs_message = extract_text_from_bytearray(data)
        print(f"APRS message received: {aprs_message}")
        asyncio.create_task(self.matrix_client.room_send(
                room_id=self.room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": f"{aprs_message}"
                }
            ))

        # Check if the message is in the "<username>: <text>" format
        # if ":" in aprs_message:
        #     sender, message = aprs_message.split(":", 1)
        #     asyncio.create_task(self.matrix_client.room_send(
        #         room_id=self.room_id,
        #         message_type="m.room.message",
        #         content={
        #             "msgtype": "m.text",
        #             "body": f"{sender}: {message.strip()}"
        #         }
        #     ))
        #     print(f"Forwarded to Matrix room: {sender}: {message.strip()}")

# Function to send APRS message from Matrix message
async def handle_matrix_message(event, aprs_engine):
    print(vars(event))

    if isinstance(event, RoomMessageText):
        sender = event.sender
        message = event.body

        aprs_message = f"{sender}: {message}"
        aprs_engine.send_unproto(0, "K3DEP", "APRS", aprs_message, ["WIDE1-1"])
        print(f"Forwarded to APRS: {aprs_message}")

# Main function to start the APRS and Matrix bot
async def main(matrix_server, matrix_room, matrix_username, matrix_password):
    # Initialize the Matrix client
    matrix_client = AsyncClient(matrix_server, matrix_username)
    
    # Login to Matrix
    response = await matrix_client.login(matrix_password)
    if isinstance(response, LoginResponse):
        print(f"Logged in as {matrix_username}")
    else:
        print(f"Failed to login: {response}")
        return

    # Join the room
    await matrix_client.join(matrix_room)

    # Create an Application instance for APRS
    app = pe.app.Application()

    # Add our custom receive handler to the application
    app.use_custom_handler(MyReceiveHandler(matrix_client, matrix_room))

    # Start APRS application and connect to the server
    server_host = 'inovato'
    server_port = 8000
    app.start(server_host, server_port)

    # Enable monitoring
    app.enable_monitoring = True

    # Listen for messages in Matrix room
    def on_room_message(event, room):
        asyncio.create_task(handle_matrix_message(event, app.engine))

    matrix_client.add_event_callback(on_room_message, RoomMessage)

    print(f"Connected to Matrix server: {matrix_server}, Room: {matrix_room}")
    print("Connected to APRS server, monitoring messages...")

    # Run both the APRS and Matrix clients asynchronously
    await asyncio.gather(
        matrix_client.sync_forever(timeout=30000),
        #asyncio.to_thread(app.run)  # Run the APRS application in a separate thread
    )

    app.stop()

# Parse command-line arguments
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APRS to Matrix Bridge")
    parser.add_argument('--matrix-server', type=str, required=False, default='http://wart:8008', help="Matrix server hostname")
    parser.add_argument('--matrix-room', type=str, required=False, default='Testing', help="Matrix room to join")
    parser.add_argument('--matrix-username', type=str, default="aprs_bot", help="Matrix bot username")
    parser.add_argument('--matrix-password', type=str, required=True, help="Matrix bot password")
    args = parser.parse_args()

    # Run the APRS and Matrix bridge
    asyncio.run(main(args.matrix_server, args.matrix_room, args.matrix_username, args.matrix_password))

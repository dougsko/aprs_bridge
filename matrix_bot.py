#!/usr/bin/env python3

import asyncio
from nio import AsyncClient, LoginResponse, RoomMessageText, ClientConfig
import ssl
import certifi
from httpx import Client

# Custom function to disable SSL verification for self-signed certs
def create_insecure_ssl_context():
    # Create an SSL context that ignores verification
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)  # Force TLSv1.2
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context

# Basic Matrix bot function
async def basic_matrix_bot():
    # Matrix server, username, password, and room details
    matrix_server = "http://inovato:8008"  # Use HTTPS and port 8448 for the Matrix server
    matrix_username = "aprs_bot"
    matrix_password = "dougsko123"
    matrix_room = "!testing:inovato:8008"

    # SSL context to disable certificate verification (for self-signed certs)
    ssl_context = create_insecure_ssl_context()

    # Initialize the Matrix client and disable SSL verification
    config = ClientConfig()
    matrix_client = AsyncClient(matrix_server, matrix_username, config=config)
    matrix_client.transport_adapter = Client(verify=ssl_context)  # Disable SSL verification

    # Login to Matrix
    response = await matrix_client.login(matrix_password)
    
    # Check if login was successful
    if isinstance(response, LoginResponse):
        print(f"Logged in as {matrix_username}")

        # Join the room
        await matrix_client.join(matrix_room)
        print(f"Joined room: {matrix_room}")

        # Send "Hello" message to the room
        await matrix_client.room_send(
            room_id=matrix_room,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": "Hello"
            }
        )
        print("Sent 'Hello' to the room")

        # Event callback to echo messages heard in the room to the console
        async def message_callback(room, event):
            if isinstance(event, RoomMessageText):
                sender = event.sender
                message = event.body
                print(f"Message from {sender}: {message}")

        # Add the callback to handle messages
        matrix_client.add_event_callback(message_callback, RoomMessageText)

        # Sync to keep listening for events
        await matrix_client.sync_forever(timeout=30000)
    else:
        print(f"Failed to login: {response}")

    # Close the Matrix client
    await matrix_client.close()

# Run the bot
if __name__ == "__main__":
    asyncio.run(basic_matrix_bot())

#!/usr/bin/env python3

#!/usr/bin/env python3

import asyncio
from nio import AsyncClient, LoginResponse, RoomMessageText

# Basic Matrix bot function
async def basic_matrix_bot():
    # Matrix server, username, password, and room details
    matrix_server = "http://wart:8008"
    matrix_username = "aprs_bot"
    matrix_password = "dougsko123"
    matrix_room = "testing"

    # Initialize the Matrix client
    matrix_client = AsyncClient(matrix_server, matrix_username)

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

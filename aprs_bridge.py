#!/usr/bin/env python3

import pe
import pe.app
import logging

import random

def create_aprs_message(dest_callsign: str, message: str) -> bytearray:
    # Step 1: Pad the destination callsign to 9 characters
    padded_callsign = dest_callsign.ljust(9)[:9]  # Ensure it's exactly 9 characters

    # Step 2: Generate a random acknowledgment ID (between 10 and 99, for example)
    ack_id = str(random.randint(10, 99))

    # Step 3: Construct the APRS message
    aprs_message = f':{padded_callsign}:{message}{{{ack_id}}}'

    # Step 4: Return the message as a bytearray
    return bytearray(aprs_message, 'utf-8')


def extract_text_from_bytearray(data: bytearray) -> str:
    # Convert the bytearray to a string
    text = data.decode('utf-8', errors='ignore')

    # Find the position of the second colon
    start = text.find(':', text.find(':') + 1) + 1

    # Find the position of the opening curly brace
    end = text.find('{')

    # Extract and return the text between the second colon and the curly brace
    if start != -1 and end != -1:
        return text[start:end].strip()
    else:
        return ''  # Return an empty string if the delimiters are not found


# Configure logging to capture debug output
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('pe.handler')

# Define a custom receive handler to process messages
class MyReceiveHandler(pe.ReceiveHandler):
    def monitored_own(self, port, call_from, call_to, text, data):
        print(f"My Own frame: Port={port}, From={call_from}, To={call_to}, Text={text}, Data={data}")
        print(extract_text_from_bytearray(data))

    def monitored_connected(self, port, call_from, call_to, text, data):
        # Print information about the connected frames
        print(f"Connected frame: Port={port}, From={call_from}, To={call_to}, Text={text}, Data={data}")

    def monitored_supervisory(self, port, call_from, call_to, text):
        # Print information about supervisory frames
        print(f"Supervisory frame: Port={port}, From={call_from}, To={call_to}, Text={text}")

    def monitored_unproto(self, port, call_from, call_to, text, data):
        # Print information about unproto frames
        print(f"Unproto frame: Port={port}, From={call_from}, To={call_to}, Text={text}, Data={data}")

    def monitored_raw(self, port, data):
        # Print raw AX.25 frames
        print(f"Raw frame: Port={port}, Data={data}")

# Create an Application instance
app = pe.app.Application()

# Create and add a DebugReceiveHandler
#debug_handler = pe.handler.DebugReceiveHandler()
#app.use_custom_handler(debug_handler)

# Add our custom receive handler to the application
app.use_custom_handler(MyReceiveHandler())


# Define server details
server_host = '127.0.0.1'
server_port = 8000

# Start the application and connect to the server
app.start(server_host, server_port)

# Enable debug output for the DebugReceiveHandler
#debug_handler.enable_output = True

# Enable monitoring
app.enable_monitoring = True

# Run the application (this will block until you stop the app)
try:
    print("Connected to server and monitoring messages...")
    app.engine.ask_callsigns_heard_on_port(0)  # Optionally ask for heard callsigns
    #app.register_callsigns("K3DEP")
    app.send_unproto(0, "K4DEP", "APRS", create_aprs_message("APRS", "HEY THERE"))
    # Keep running until interrupted
#    app.run()  # This call will block until `app.stop()` is called
except KeyboardInterrupt:
    # Stop the application when interrupted
    app.stop()


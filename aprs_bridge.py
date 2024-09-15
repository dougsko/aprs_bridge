#!/usr/bin/env python3

import pe
import pe.app
import logging

# Configure logging to capture debug output
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('pe.handler')

# Define a custom receive handler to process messages
class MyReceiveHandler(pe.ReceiveHandler):
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
debug_handler = pe.handler.DebugReceiveHandler()
app.use_custom_handler(debug_handler)

# Define server details
server_host = '127.0.0.1'
server_port = 8000

# Start the application and connect to the server
app.start(server_host, server_port)

# Enable debug output for the DebugReceiveHandler
debug_handler.enable_output = True

# Add our custom receive handler to the application
app.use_custom_handler(MyReceiveHandler())

# Enable monitoring
app.enable_monitoring = True

# Run the application (this will block until you stop the app)
try:
    print("Connected to server and monitoring messages...")
    app.engine.ask_callsigns_heard_on_port(0)  # Optionally ask for heard callsigns
    # Keep running until interrupted
#    app.run()  # This call will block until `app.stop()` is called
except KeyboardInterrupt:
    # Stop the application when interrupted
    print("Stopping application...")
    app.stop()


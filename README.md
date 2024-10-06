# APRS Chat Server

This project is an asynchronous chat server built with Python using WebSockets. It integrates with an APRS (Automatic Packet Reporting System) server to exchange messages between the APRS network and WebSocket clients. The server supports message compression using zlib and stores messages in a local SQLite database.

## Features

- WebSocket-based chat server: Allows multiple clients to connect and exchange messages in real-time.
- APRS message integration: Receives and sends messages to an APRS server, converting between WebSocket and APRS formats.
- Message compression: Supports optional message compression using zlib to reduce data size.
- SQLite storage: Persists chat history in a SQLite database and maintains a rolling buffer of messages.
- Graceful shutdown: Handles shutdown signals (SIGINT, SIGTERM) to cleanly close client connections and the database.

## Requirements

- Python 3.x
- The following Python libraries:
  - asyncio
  - websockets
  - sqlite3 (built-in with Python)
  - zlib (built-in with Python)
  - base64 (built-in with Python)
  - json (built-in with Python)
  - pe (A custom library to interface with the APRS system)

### Install Dependencies

To install the required libraries, run:

pip install websockets pyham_pe

## Configuration

You can customize the following parameters within the script:

- WebSocket server:
  - HOST: The host for the WebSocket server (default: '0.0.0.0').
  - PORT: The port for the WebSocket server (default: 6789).
  
- SQLite:
  - DB_NAME: The name of the SQLite database file (default: 'chat_messages.db').
  - TABLE_NAME: The table name used to store messages (default: 'messages').
  - MAX_ROWS: The maximum number of rows stored in the SQLite database before old rows are deleted (default: 100).

- APRS Integration:
  - APRS_SERVER_HOST: The APRS server host (default: 'orangepizero2w').
  - APRS_SERVER_PORT: The APRS server port (default: 8002).
  - APRS_SRC_CALLSIGN: The source APRS callsign (default: 'K3DEP').
  - APRS_DEST_CALLSIGN: The destination APRS callsign (default: 'APRS').
  - USE_COMPRESSION: Flag to enable/disable message compression (default: True).

## How to Run

1. Clone the repository or download the script.

2. Run the script using Python 3:

   python3 chat_server.py

3. The server will start, and you can connect to it using a WebSocket client at ws://<HOST>:<PORT>.

4. APRS messages will be received and sent from/to the APRS server.

## How It Works

### WebSocket Clients

- WebSocket clients can connect to the server by providing a username.
- Once connected, clients receive the chat history and can broadcast messages.
- Messages from WebSocket clients are stored in an SQLite database and optionally sent to the APRS network.

### APRS Integration

- The server listens for messages from the APRS server using the APRSReceiveHandler class.
- When a message is received from the APRS network, it is broadcast to all connected WebSocket clients.
- Messages sent by WebSocket clients are also transmitted to the APRS network.

### Database Storage

- Messages are stored in a local SQLite database (chat_messages.db).
- The server automatically removes old messages when the number of stored rows exceeds MAX_ROWS.

## Handling Disconnects

When a WebSocket client disconnects or refreshes the browser, the server handles the following scenarios:

- WebSocket disconnects: Clients are automatically removed if a 1001 (going away) WebSocket error occurs.
- Graceful shutdown: When the server receives a SIGINT or SIGTERM signal, it shuts down gracefully by closing all connections and the database.

## Error Handling

The server attempts to handle common errors such as:

- Failed WebSocket message sends (ConnectionClosed).
- APRS message decoding issues.
- JSON parsing failures.

## Example Interaction

1. WebSocket Client connects to the server.
2. APRS messages are received and broadcast to all WebSocket clients.
3. WebSocket clients send messages, which are forwarded to APRS and other connected clients.

## License

This project is licensed under the MIT License.

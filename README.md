# APRS Chat Server

This project is a chat server that facilitates real-time communication via WebSockets and APRS (Automatic Packet Reporting System). It includes an HTTP server to serve a web-based chat client (`web_client.html`).

## Features
- Real-time WebSocket-based messaging
- APRS integration for radio-based messaging
- Persistent chat history using SQLite
- HTTP server to serve a web-based client
- Automatic message cleanup to maintain database size

## Installation

1. **Clone the repository:**
   ```sh
   git clone <repository_url>
   cd chat-server
   ```

2. **Install dependencies:**
   ```sh
   pip install websockets pe sqlite3 configparser
   ```

3. **Configure the server:**
   The server configuration is stored in `chat_server.conf`. If not present, it will be created on the first run. Modify the settings as needed.

4. **Run the server:**
   ```sh
   ./chat_server.py
   ```

## Configuration
The `chat_server.conf` file includes the following parameters:

- `SRC_CALLSIGN`: Your source callsign for APRS
- `DEST_CALLSIGN`: Destination callsign for APRS messages
- `WEBSOCKET_HOST`: WebSocket server address
- `WEBSOCKET_PORT`: Port for WebSocket communication
- `HTTP_PORT`: Port for serving the web client
- `AGW_SERVER`: Address of the AGWPE-compatible server
- `AGW_PORT`: AGWPE server port
- `DB_NAME`: SQLite database filename
- `TABLE_NAME`: Table name for storing chat messages
- `MAX_ROWS`: Maximum stored messages before older ones are deleted
- `WEB_CLIENT_NAME`: HTML file served as the chat client
- `USE_COMPRESSION`: Whether to compress APRS messages

## Web Client

The `web_client.html` file serves as the front-end interface for chat. It connects to the WebSocket server and displays messages in real-time.

To access it, open your browser and navigate to:
```
http://localhost:<HTTP_PORT>/
```
Replace `<HTTP_PORT>` with the configured HTTP server port.

## Database Structure
The SQLite database stores chat messages with the following schema:
```
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    username TEXT NOT NULL,
    message TEXT NOT NULL
);
```

## Troubleshooting
- If messages appear twice, ensure that `store_message` is not called both in `broadcast` and `handle_aprs_message`.
- If `chat_server.conf` is missing, run the script once to generate it.
- Ensure APRS and AGW server settings are correct for radio-based messaging.

## License
This project is open-source and available under the MIT License.


# Aetheric Engine TCP Client

This Python script connects to the mysterious "Aetheric Engine" via TCP, authenticates using a JWT token, listens for both ASCII and binary messages, and logs them to an SQLite database.

## Features

- ✅ TCP socket connection
- ✅ JWT-based authentication
- ✅ Parses ASCII and binary message formats
- ✅ Writes to SQLite with full metadata
- ✅ Handles decoding (UTF-8, Latin-1, Base64 fallback)
- ✅ Validates ASCII formatting rules
- ✅ Logs all events/errors to `ae_client_log.txt`

---

## 🔧 How It Works

### 1. Connect to the Server
- Uses Python’s built-in `socket` library.
- Sends the authentication command:  
  `AUTH <JWT_Token>`

### 2. Receive and Parse Messages
- Data is streamed continuously — proper buffer management is essential.

#### ASCII Messages
- Start with `$`, end with `;`.
- Payload must be **≥5 printable characters**, excluding `$` and `;`.

#### Binary Messages
- Start with **byte `0xAA`**.
- Next **5 bytes**: big-endian integer indicating the payload size.
- Followed by the **payload**: random bytes.

### 3. Write to SQLite
- Uses Python’s `sqlite3` module.
- Stores messages with metadata:
  - `payload`, `length`, `received_at`, `decoded`, and `valid`

### 4. Termination
- Stops after receiving **600 messages**.
- Sends the command: `STATUS`  
- Then closes the socket connection.

### 5. Validation App
- An independent script validates all saved messages by:
  - Connecting to the same SQLite DB
  - Ensuring **no malformed or partial messages**
  - Confirming **≥600 total messages received and parsed correctly**

---

## Setup

1. **Clone the repository**

```bash
git clone https://github.com/kane213426/aetheric-engine-client.git
cd aetheric-engine-client
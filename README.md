# Aetheric Engine TCP Client (Fully AI Generated)

This is a Python TCP client that connects to the mysterious Aetheric Engine, authenticates with a JWT, and captures both ASCII and binary messages in real-time. The messages are parsed, validated, and stored in a local SQLite database with full metadata. The codes here are fully AI generated. 

---

## 🔧 Features

- ✅ Connects via TCP and authenticates using JWT
- ✅ Parses **ASCII** and **binary** messages from a custom byte stream
- ✅ Stores messages with full metadata:
  - `payload`, `length`, `received_at`, `decoded`, `valid`
- ✅ Handles partial binary messages across multiple TCP packets
- ✅ Trims `ae_client_log.txt` to the most recent 5000 lines
- ✅ Stops automatically after 600 messages (combined)
- ✅ Designed for robustness and real-world network irregularities

---

## 📜 Message Format

### ASCII Messages
- Start with `$` and end with `;`
- Payload: 5 or more printable characters (excluding `$` or `;`)

### Binary Messages
| Offset | Size (byte) | Description                  |
|--------|-------------|------------------------------|
| 0      | 1           | Header byte: `0xAA`          |
| 1      | 5           | Big-endian integer (payload size) |
| 6      | N           | Binary payload of size `N`   |

---

## 💾 Database Schema

### `msgascii`
| Column       | Type      |
|--------------|-----------|
| id           | INTEGER   |
| payload      | TEXT      |
| length       | INTEGER   |
| received_at  | DATETIME  |
| decoded      | TEXT      |
| valid        | BOOLEAN   |

### `msgbinary`
| Column       | Type      |
|--------------|-----------|
| id           | INTEGER   |
| payload      | BLOB      |
| length       | INTEGER   |
| received_at  | DATETIME  |
| decoded      | TEXT      |
| valid        | BOOLEAN   |

---

## 🚀 How It Works

1. **Connect to the Server**
   - Uses Python’s `socket` to connect to the AE server
   - Sends `AUTH <JWT_TOKEN>` upon connection

2. **Receive and Parse Messages**
   - Buffers incoming bytes
   - Extracts ASCII messages based on `$...;`
   - Extracts binary messages based on header `0xAA` + 5-byte size + payload
   - Handles incomplete binary messages across recv() calls

3. **Store to SQLite**
   - Saves messages with detailed metadata
   - Database file: `ae_messages.db`

4. **Log Output**
   - Logs to `ae_client_log.txt`
   - File is truncated to 5000 lines to limit disk usage

5. **Termination**
   - Stops after receiving 600 total messages
   - Sends `STATUS` to gracefully end the session

---

## 📂 Files

- `ae_client.py` — main TCP client and parser
- `ae_messages.db` — SQLite DB file storing all messages
- `ae_client_log.txt` — log file (auto-truncated)
- `README.md` — this file

---

## 🧠 Notes

- Some binary messages may be very large (up to 200GB reported)
- Message streaming is continuous and unbounded
- Forensic analysis is easier with both raw and decoded payloads

---

## 🔐 Auth Details

- Replace `JWT_TOKEN` in `ae_client.py` with your token
- Token expires after 2025-05-22

---

## 🛠 Requirements

- Python 3.8+
- No external dependencies (only uses standard library)

---

## 🧑‍💻 Run the Client

```bash
python ae_client.py

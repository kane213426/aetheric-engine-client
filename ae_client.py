import socket
import sqlite3
import base64
from datetime import datetime, timezone

# --- Configuration ---
SERVER_IP = '35.213.160.152'  # AE server IP
SERVER_PORT = 8080  # AE server port
JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJrYW5ldHNlMTIzQGdtYWlsLmNvbSIsImp0aSI6IjE5NTg4MzM4LWI3YzItNDI0YS1iMGE0LWFjNzliNjVhNmRhZSIsIm5iZiI6MTc0NjYzNDM4OCwiZXhwIjoxNzQ3ODQzOTg4LCJpYXQiOjE3NDY2MzQzODgsImlzcyI6IlByb2dyYW1taW5nU2tpbGxDaGFsbGVuZ2UiLCJhdWQiOiJJbnRlcnZpZXdlZXMifQ.y3EvlCNgxOPSyUc9qq5v52DGwAQuinJfLWyy2oUxUQs'  # JWT token from AE curator
DB_PATH = 'ae_messages.db'  # SQLite database file path
LOG_PATH = 'ae_client_log.txt'  # Log file for status, parsing, and errors
MAX_MESSAGES = 600  # Stop after collecting 600 messages total (ASCII + binary)

# --- Logging utility ---


def log(msg):
    """
    Appends a timestamped message to the log and truncates the file
    to the last 5000 lines to prevent uncontrolled growth.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"[{timestamp}] {msg}\n"

    # Append message to log file
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line)

    # Truncate to last 5000 lines
    try:
        with open(LOG_PATH, 'r+', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) > 5000:
                f.seek(0)
                f.writelines(lines[-5000:])
                f.truncate()
    except Exception as e:
        print(f"⚠️ Failed to truncate log: {e}")


# --- SQLite database setup ---
# Connect to the DB and create tables if they don't exist
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS msgascii (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT,
    length INTEGER,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    decoded TEXT,
    valid BOOLEAN
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS msgbinary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload BLOB,
    length INTEGER,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    decoded TEXT,
    valid BOOLEAN
)
""")
conn.commit()

message_count = 0  # Shared counter for all messages saved

# --- ASCII message handler ---


def save_ascii(payload):
    """
    Save a parsed ASCII message along with its metadata.
    """
    global message_count
    length = len(payload)
    is_valid = length >= 5 and ('$' not in payload and ';' not in payload)
    received_at = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO msgascii (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (payload, length, received_at, payload, is_valid))
    conn.commit()
    message_count += 1
    log(f"💬 ASCII message #{message_count} saved: {payload[:30]}")
    print(f"📈 Total messages so far: {message_count}")

# --- Binary message handler ---


def save_binary(full_binary_message):
    """
    Save a parsed binary message along with metadata and attempted decoding.
    """
    global message_count
    # Strip off header (1 byte) + size (5 bytes)
    payload = full_binary_message[6:]
    length = len(payload)
    received_at = datetime.now(timezone.utc).isoformat()

    # Try decoding the binary payload to readable text
    try:
        decoded = payload.decode('utf-8')
    except UnicodeDecodeError:
        try:
            decoded = payload.decode('latin-1')
        except UnicodeDecodeError:
            decoded = base64.b64encode(payload).decode('ascii')  # fallback

    cursor.execute("""
        INSERT INTO msgbinary (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (full_binary_message, length, received_at, decoded, True))
    conn.commit()
    message_count += 1
    log(f"📦 Binary message #{message_count} saved ({length} bytes)")
    print(f"📈 Total messages so far: {message_count}")

# --- Message parsing logic ---


def parse_buffer(buffer, save_ascii_callback, save_binary_callback, max_messages, current_count):
    """
    Parses incoming byte stream to extract and save ASCII and binary messages.
    Maintains and returns the updated buffer and message count.
    """
    while current_count < max_messages:
        log(f"📥 Buffer size: {len(buffer)} bytes")

        # --- ASCII message extraction ---
        while b'$' in buffer and b';' in buffer:
            start = buffer.find(b'$')
            end = buffer.find(b';', start)
            if start == -1 or end == -1:
                log("🔍 ASCII: Incomplete markers found")
                break
            if end - start - 1 >= 5:
                try:
                    payload = buffer[start + 1:end].decode('ascii')
                    log(f"💬 Found ASCII message: {payload[:30]}")
                    save_ascii_callback(payload)
                    current_count += 1
                except UnicodeDecodeError:
                    log("❌ ASCII decode error, skipping")
                buffer = buffer[end + 1:]
            else:
                log("⚠️ ASCII message too short, skipping")
                buffer = buffer[end + 1:]

        # --- Binary message extraction ---
        while True:
            start = buffer.find(b'\xAA')  # Look for 0xAA header byte
            if start == -1:
                log("🔍 No binary header (0xAA) found")
                break

            log(f"🔍 Found 0xAA at index {start} (buffer len: {len(buffer)})")

            # Ensure buffer is long enough for 5-byte size field
            if start + 6 > len(buffer):
                log("⏳ Found 0xAA but not enough space for 5-byte size field. Waiting for more.")
                break

            # Read 5-byte big-endian payload size
            size = int.from_bytes(buffer[start + 1:start + 6], byteorder='big')

            # Sanity check: skip if size is absurd
            if size > 100_000_000:
                log(f"❌ Skipping invalid binary size: {size}")
                buffer = buffer[start + 1:]
                continue

            total_len = start + 6 + size
            if len(buffer) < total_len:
                log(
                    f"⏳ Incomplete binary message: need {total_len}, have {len(buffer)} — retrying after next recv()")
                break

            # Extract and save full binary message
            full_message = buffer[start:total_len]
            log(f"📦 Found binary message ({size} bytes)")
            save_binary_callback(full_message)
            current_count += 1
            buffer = buffer[total_len:]

        if current_count >= max_messages:
            break

    return buffer, current_count

# --- Socket receive loop ---


def parse_and_store(sock):
    """
    Receives streamed data from AE and hands it to the parser until 600 messages are saved.
    """
    global message_count
    buffer = b''

    while message_count < MAX_MESSAGES:
        data = sock.recv(8192)
        if not data:
            break
        buffer += data

        buffer, message_count = parse_buffer(
            buffer,
            save_ascii_callback=save_ascii,
            save_binary_callback=save_binary,
            max_messages=MAX_MESSAGES,
            current_count=message_count
        )

    # Send STATUS command to end stream
    sock.sendall(b'STATUS\n')
    sock.close()
    conn.close()
    log("🛑 AE has stopped talking.")
    print("📡 AE has stopped talking.")

# --- Main entry point ---


def main():
    """
    Establish connection, authenticate, and begin message capture.
    """
    log("🌐 Connecting to AE server...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.sendall(f'AUTH {JWT_TOKEN}\n'.encode())
    log("🔐 AUTH sent. Listening for messages...")
    parse_and_store(sock)
    log(f"✅ Finished. Total messages saved: {message_count}")


if __name__ == '__main__':
    main()

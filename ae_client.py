import socket
import sqlite3
import base64
from datetime import datetime, timezone

# --- Configuration ---
# These are settings used to connect to the Aetheric Engine server and manage the local setup.
SERVER_IP = '35.213.160.152'  # The IP address of the remote AE server
SERVER_PORT = 8080            # The port to connect to on the AE server
JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJrYW5ldHNlMTIzQGdtYWlsLmNvbSIsImp0aSI6IjE5NTg4MzM4LWI3YzItNDI0YS1iMGE0LWFjNzliNjVhNmRhZSIsIm5iZiI6MTc0NjYzNDM4OCwiZXhwIjoxNzQ3ODQzOTg4LCJpYXQiOjE3NDY2MzQzODgsImlzcyI6IlByb2dyYW1taW5nU2tpbGxDaGFsbGVuZ2UiLCJhdWQiOiJJbnRlcnZpZXdlZXMifQ.y3EvlCNgxOPSyUc9qq5v52DGwAQuinJfLWyy2oUxUQs'  # Authorization token for access
# Local file path where messages will be stored in a database
DB_PATH = 'ae_messages.db'
LOG_PATH = 'ae_client_log.txt'  # File where activity logs will be written
MAX_MESSAGES = 600           # Stop after receiving this many messages
# Limit buffer size to avoid memory issues (1 GB max)
MAX_BUFFER_SIZE = 1_000_000_000

# --- Logging utility ---
# This function logs every action taken by the script along with a timestamp.
# It ensures the log file stays small by keeping only the last 5000 lines.


def log(msg):
    timestamp = datetime.now(timezone.utc).isoformat()  # Get current UTC time
    line = f"[{timestamp}] {msg}\n"  # Format message
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line)  # Append to file
    try:
        with open(LOG_PATH, 'r+', encoding='utf-8') as f:
            lines = f.readlines()
            if len(lines) > 5000:
                f.seek(0)  # Go to start of file
                f.writelines(lines[-5000:])  # Keep only last 5000 lines
                f.truncate()  # Remove rest
    except Exception as e:
        print(f"⚠️ Failed to truncate log: {e}")


# --- SQLite DB setup ---
# Connect to a local SQLite database and ensure the two tables exist.
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Table for ASCII messages with metadata
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

# Table for binary messages with metadata
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

message_count = 0  # Counter for total number of saved messages

# --- Save ASCII ---
# This function stores an ASCII message in the database and logs it.


def save_ascii(payload):
    global message_count
    length = len(payload)
    is_valid = length >= 5 and (
        '$' not in payload and ';' not in payload)  # Check message is valid
    received_at = datetime.now(timezone.utc).isoformat()

    # Insert into the ASCII table
    cursor.execute("""
        INSERT INTO msgascii (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (payload, length, received_at, payload, is_valid))
    conn.commit()
    message_count += 1
    log(f"💬 ASCII message #{message_count} saved: {payload[:30]}")
    print(f"📈 Total messages so far: {message_count}")

# --- Save Binary ---
# This function processes and saves binary messages with decoding attempts.


def save_binary(full_binary_message):
    global message_count
    # Skip header and size fields (first 6 bytes)
    payload = full_binary_message[6:]
    length = len(payload)
    received_at = datetime.now(timezone.utc).isoformat()

    # Attempt to decode the binary data
    try:
        decoded = payload.decode('utf-8')
    except UnicodeDecodeError:
        try:
            decoded = payload.decode('latin-1')
        except UnicodeDecodeError:
            decoded = base64.b64encode(payload).decode(
                'ascii')  # If all else fails, base64 encode it

    # Insert into the binary table
    cursor.execute("""
        INSERT INTO msgbinary (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (full_binary_message, length, received_at, decoded, True))
    conn.commit()
    message_count += 1
    log(f"📦 Binary message #{message_count} saved ({length} bytes)")
    print(f"📈 Total messages so far: {message_count}")

# --- Parser ---
# This function extracts both ASCII and binary messages from the incoming byte buffer.


def parse_buffer(buffer, save_ascii_callback, save_binary_callback, max_messages, current_count):
    while current_count < max_messages:
        log(f"📥 Buffer size: {len(buffer)} bytes")

        if len(buffer) > MAX_BUFFER_SIZE:
            log("🚨 Buffer exceeded safe threshold. Clearing buffer to prevent memory overflow.")
            buffer = b''
            break

        # --- Parse ASCII Messages ---
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

        # --- Parse Binary Messages ---
        while True:
            start = buffer.find(b'\xAA')  # Look for binary start marker
            if start == -1:
                log("🔍 No binary header (0xAA) found")
                break

            if start + 6 > len(buffer):
                log("⏳ Not enough bytes for binary header + size field")
                break

            size = int.from_bytes(
                # Get payload size
                buffer[start + 1:start + 6], byteorder='big')

            if size > 100_000_000:
                log(f"❌ Skipping invalid binary size: {size}")
                buffer = buffer[start + 1:]  # Skip and move forward
                continue

            total_len = start + 6 + size
            if len(buffer) < total_len:
                log(
                    f"⏳ Incomplete binary message: need {total_len}, have {len(buffer)}")
                break

            # Slice the full binary message
            full_message = buffer[start:total_len]
            log(f"📦 Found binary message ({size} bytes)")
            save_binary_callback(full_message)
            current_count += 1
            buffer = buffer[total_len:]

        if current_count >= max_messages:
            break

    return buffer, current_count

# --- Socket wrapper ---
# Receives incoming messages and calls the parser until message limit is hit.


def parse_and_store(sock):
    global message_count
    buffer = b''

    while message_count < MAX_MESSAGES:
        try:
            data = sock.recv(8192)  # Read up to 8192 bytes
        except ConnectionResetError:
            log("❌ Connection reset by server")
            break

        if not data:
            log("⚠️ Server closed connection early")
            break

        buffer += data
        buffer, message_count = parse_buffer(
            buffer,
            save_ascii_callback=save_ascii,
            save_binary_callback=save_binary,
            max_messages=MAX_MESSAGES,
            current_count=message_count
        )

    try:
        sock.sendall(b'STATUS\n')  # Tell AE to stop sending
    except Exception as e:
        log(f"⚠️ Failed to send STATUS: {e}")
    sock.close()
    conn.close()
    log("🛑 AE has stopped talking.")
    print("📡 AE has stopped talking.")

# --- Main function ---
# Starts the process: connects, authenticates, and receives messages.


def main():
    log("🌐 Connecting to AE server...")
    try:
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)  # Create socket
        sock.connect((SERVER_IP, SERVER_PORT))  # Connect to server
        sock.sendall(f"AUTH {JWT_TOKEN}\n".encode())  # Send AUTH token
        log("🔐 AUTH sent. Listening for messages...")
        parse_and_store(sock)  # Begin message parsing
    except Exception as e:
        log(f"❌ Connection failed: {e}")
    log(f"✅ Finished. Total messages saved: {message_count}")


if __name__ == '__main__':
    main()

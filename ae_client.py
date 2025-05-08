import socket
import sqlite3
import base64
from datetime import datetime, timezone

# --- Configuration ---
SERVER_IP = '35.213.160.152'
SERVER_PORT = 8080
JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJrYW5ldHNlMTIzQGdtYWlsLmNvbSIsImp0aSI6IjE5NTg4MzM4LWI3YzItNDI0YS1iMGE0LWFjNzliNjVhNmRhZSIsIm5iZiI6MTc0NjYzNDM4OCwiZXhwIjoxNzQ3ODQzOTg4LCJpYXQiOjE3NDY2MzQzODgsImlzcyI6IlByb2dyYW1taW5nU2tpbGxDaGFsbGVuZ2UiLCJhdWQiOiJJbnRlcnZpZXdlZXMifQ.y3EvlCNgxOPSyUc9qq5v52DGwAQuinJfLWyy2oUxUQs'

DB_PATH = 'ae_messages.db'
LOG_PATH = 'ae_client_log.txt'
MAX_MESSAGES = 600

# --- Logging utility ---


def log(msg):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {msg}\n")


# --- SQLite setup ---
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Drop existing tables (fresh start)
cursor.execute("DROP TABLE IF EXISTS msgascii")
cursor.execute("DROP TABLE IF EXISTS msgbinary")

# Recreate tables with full metadata
cursor.execute("""
CREATE TABLE msgascii (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT,
    length INTEGER,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    decoded TEXT,
    valid BOOLEAN
)
""")

cursor.execute("""
CREATE TABLE msgbinary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload BLOB,
    length INTEGER,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    decoded TEXT,
    valid BOOLEAN
)
""")

conn.commit()

message_count = 0

# --- Save functions ---


def save_ascii(payload):
    global message_count
    length = len(payload)
    is_valid = length >= 5 and ('$' not in payload and ';' not in payload)

    cursor.execute("""
        INSERT INTO msgascii (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (payload, length, datetime.now(timezone.utc), payload, is_valid))
    conn.commit()
    message_count += 1
    log(f"💬 ASCII message #{message_count} saved: {payload[:30]}")


def save_binary(full_binary_message):
    global message_count
    payload = full_binary_message[6:]
    length = len(payload)

    try:
        decoded = payload.decode('utf-8')
    except UnicodeDecodeError:
        try:
            decoded = payload.decode('latin-1')
        except UnicodeDecodeError:
            decoded = base64.b64encode(payload).decode('ascii')

    cursor.execute("""
        INSERT INTO msgbinary (payload, length, received_at, decoded, valid)
        VALUES (?, ?, ?, ?, ?)
    """, (full_binary_message, length, datetime.now(timezone.utc), decoded, True))
    conn.commit()
    message_count += 1
    log(f"📦 Binary message #{message_count} saved ({length} bytes)")

# --- Parser ---


def parse_buffer(buffer, save_ascii_callback, save_binary_callback, max_messages, current_count):
    while current_count < max_messages:
        while b'$' in buffer and b';' in buffer:
            start = buffer.find(b'$')
            end = buffer.find(b';', start)
            if start == -1 or end == -1:
                break
            if end - start - 1 >= 5:
                try:
                    payload = buffer[start + 1:end].decode('ascii')
                    save_ascii_callback(payload)
                    current_count += 1
                except UnicodeDecodeError:
                    pass
                buffer = buffer[end + 1:]
            else:
                break

        while True:
            start = buffer.find(b'\xAA')
            if start == -1 or len(buffer) - start < 6:
                break
            size = int.from_bytes(buffer[start + 1:start + 6], byteorder='big')
            total_len = start + 6 + size
            if len(buffer) < total_len:
                break
            full_message = buffer[start:total_len]
            save_binary_callback(full_message)
            current_count += 1
            buffer = buffer[total_len:]

        if current_count >= max_messages:
            break

    return buffer, current_count

# --- Main receive loop ---


def parse_and_store(sock):
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

    sock.sendall(b'STATUS\n')
    sock.close()
    conn.close()
    log("🛑 AE has stopped talking.")
    print("📡 AE has stopped talking.")

# --- Main entry point ---


def main():
    log("🌐 Connecting to AE server...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.sendall(f'AUTH {JWT_TOKEN}\n'.encode())
    log("🔐 AUTH sent. Listening for messages...")
    parse_and_store(sock)
    log(f"✅ Finished. Total messages saved: {message_count}")


if __name__ == '__main__':
    main()

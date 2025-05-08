import socket
import sqlite3

# Configuration
SERVER_IP = '35.213.160.152'
SERVER_PORT = 8080
JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJrYW5ldHNlMTIzQGdtYWlsLmNvbSIsImp0aSI6IjE5NTg4MzM4LWI3YzItNDI0YS1iMGE0LWFjNzliNjVhNmRhZSIsIm5iZiI6MTc0NjYzNDM4OCwiZXhwIjoxNzQ3ODQzOTg4LCJpYXQiOjE3NDY2MzQzODgsImlzcyI6IlByb2dyYW1taW5nU2tpbGxDaGFsbGVuZ2UiLCJhdWQiOiJJbnRlcnZpZXdlZXMifQ.y3EvlCNgxOPSyUc9qq5v52DGwAQuinJfLWyy2oUxUQs'  # Replace with your JWT if this is cleared
DB_PATH = 'ae_messages.db'
MAX_MESSAGES = 600  # Stop after collecting 600 messages

# --- Setup SQLite database and tables ---
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create tables if they don't already exist
cursor.execute('''CREATE TABLE IF NOT EXISTS msgascii (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS msgbinary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload BLOB
)''')
conn.commit()

message_count = 0  # Tracks how many messages have been saved so far

# --- Save an ASCII message to the database ---


def save_ascii(payload):
    global message_count
    cursor.execute("INSERT INTO msgascii (payload) VALUES (?)", (payload,))
    conn.commit()
    message_count += 1

# --- Save a binary message (including header and size) to the database ---


def save_binary(full_binary_message):
    global message_count
    cursor.execute("INSERT INTO msgbinary (payload) VALUES (?)",
                   (full_binary_message,))
    conn.commit()
    message_count += 1

# --- Core message parsing function ---


def parse_buffer(buffer, save_ascii_callback, save_binary_callback, max_messages, current_count):
    while current_count < max_messages:
        # ASCII parsing
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

        # --- Parse binary messages ---
        while True:
            start = buffer.find(b'\xAA')
            if start == -1 or len(buffer) - start < 6:
                break
            if len(buffer) < start + 6:
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

# --- Main loop to receive and process messages ---


def parse_and_store(sock):
    global message_count
    buffer = b''

    while message_count < MAX_MESSAGES:
        data = sock.recv(8192)
        if not data:
            break
        buffer += data

        # Call the parser to extract messages from buffer
        buffer, message_count = parse_buffer(
            buffer,
            save_ascii_callback=save_ascii,
            save_binary_callback=save_binary,
            max_messages=MAX_MESSAGES,
            current_count=message_count
        )

    # Tell AE we're done listening
    sock.sendall(b'STATUS\n')
    sock.close()
    conn.close()
    print("📡 AE has stopped talking.")

# --- Entry point to connect and authenticate ---


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.sendall(f'AUTH {JWT_TOKEN}\n'.encode())
    parse_and_store(sock)


# Run the client
if __name__ == '__main__':
    main()

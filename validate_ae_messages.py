import sqlite3
import string
import base64

DB_PATH = 'ae_messages.db'  # Path to your SQLite database file

# --- Truncate long payloads for safe and clean display ---


def truncate_payload(payload, max_length=80):
    """
    Uses repr() to convert payload into a safe printable string.
    Truncates the result if it exceeds max_length and appends '...'.
    """
    display = repr(payload)
    return display[:max_length] + "..." if len(display) > max_length else display

# --- Validate an individual ASCII message ---


def is_valid_ascii(payload):
    """
    Validates ASCII messages:
    - Must be a string
    - Must be at least 5 characters long
    - Must only contain printable characters (excluding '$' and ';')
    Returns: (True, "") if valid, else (False, reason)
    """
    if not isinstance(payload, str):
        return False, "Not a string"
    if len(payload) < 5:
        return False, "Too short (< 5 chars)"
    if any(c not in string.printable for c in payload):
        return False, "Contains non-printable characters"
    if '$' in payload or ';' in payload:
        return False, "Contains illegal chars ($ or ;)"
    return True, ""

# --- Validate an individual binary message ---


def is_valid_binary(blob):
    """
    Validates binary messages:
    - Starts with 0xAA
    - Next 5 bytes represent payload size (big-endian)
    - Actual payload must match the declared size
    Returns: (True, "") if valid, else (False, reason)
    """
    if not isinstance(blob, bytes):
        return False, "Not a byte sequence"
    if len(blob) < 6:
        return False, "Less than 6 bytes (header + size)"
    if blob[0] != 0xAA:
        return False, f"Missing header byte 0xAA, got {hex(blob[0])}"
    payload_size = int.from_bytes(blob[1:6], byteorder='big')
    if len(blob[6:]) != payload_size:
        return False, f"Payload size mismatch: expected {payload_size}, got {len(blob[6:])}"
    return True, ""

# --- Validate all ASCII messages in the database ---


def validate_ascii(cursor):
    """
    Reads and validates all rows in msgascii table.
    Returns:
    - Total count
    - Valid count
    - List of tuples: (id, valid, payload, reason)
    """
    cursor.execute("SELECT id, payload FROM msgascii")
    rows = cursor.fetchall()

    valid_count = 0
    results = []

    for msg_id, payload in rows:
        valid, reason = is_valid_ascii(payload)
        if valid:
            valid_count += 1
        results.append((msg_id, valid, payload, reason))

    return len(rows), valid_count, results

# --- Validate all binary messages in the database ---


def validate_binary(cursor):
    """
    Reads and validates all rows in msgbinary table.
    Returns:
    - Total count
    - Valid count
    - List of tuples: (id, valid, display_string, reason)
    """
    cursor.execute("SELECT id, payload FROM msgbinary")
    rows = cursor.fetchall()

    valid_count = 0
    results = []

    for msg_id, payload in rows:
        valid, reason = is_valid_binary(payload)
        display = f"<{len(payload)} bytes>"
        if valid:
            valid_count += 1
        results.append((msg_id, valid, display, reason))

    return len(rows), valid_count, results

# --- Main function to coordinate validation and print results ---


def main():
    """
    Runs validations on both ASCII and binary message tables.
    Prints a summary first, then detailed per-message results.
    """
    print("🟡 Starting validation...\n")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Run validations
    ascii_total, ascii_valid, ascii_results = validate_ascii(cursor)
    binary_total, binary_valid, binary_results = validate_binary(cursor)

    grand_total = ascii_total + binary_total
    grand_valid = ascii_valid + binary_valid
    malformed_count = grand_total - grand_valid

    # --- Print summary at the top ---
    print("📊 Summary (at the top):")
    print(f"Total messages: {grand_total}")
    print(f"Valid messages: {grand_valid}")
    print(f"Malformed messages: {malformed_count}")

    if grand_total > 600:
        print(
            f"⚠️  Received {grand_total} messages (more than 600). Not all messages may be shown.")
    elif grand_total == 600:
        print("✅ Exactly 600 messages received.")
    else:
        print("❌ Less than 600 messages received.")

    if grand_total == 0:
        print("❌ No messages found. Check your database path or parser.\n")
    elif malformed_count == 0:
        print("✅ All messages are correctly parsed.\n")
    else:
        print(
            f"❌ Some messages are malformed. ({malformed_count} of {grand_total} messages were malformed)\n")

    # --- Print results for ASCII messages ---
    print("🔤 Validating ASCII Messages...")
    if ascii_total == 0:
        print("⚠️  No ASCII messages found.")
    else:
        for msg_id, valid, payload, reason in ascii_results:
            if valid:
                # Use str() to ensure readable output (not escaped repr-style)
                print(f"msgascii #{msg_id}: ✅ RIGHT — {str(payload)}")
            else:
                display = truncate_payload(payload)
                print(
                    f"msgascii #{msg_id}: ❌ WRONG — {display} | Reason: {reason}")

    # --- Print results for binary messages ---
    print("\n🧱 Validating Binary Messages...")
    if binary_total == 0:
        print("⚠️  No binary messages found.")
    else:
        for msg_id, valid, payload_display, reason in binary_results:
            if valid:
                # Re-fetch full binary blob to extract and decode payload
                cursor.execute(
                    "SELECT payload FROM msgbinary WHERE id = ?", (msg_id,))
                row = cursor.fetchone()
                blob = row[0]
                payload_bytes = blob[6:]  # Skip header (1) + length (5)

                # Decode: UTF-8 → Latin-1 → Base64 fallback
                try:
                    decoded = payload_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        decoded = payload_bytes.decode("latin-1")
                    except UnicodeDecodeError:
                        decoded = base64.b64encode(
                            payload_bytes).decode("ascii")
                        decoded = f"<base64> {decoded}"

                print(
                    f"msgbinary #{msg_id}: ✅ RIGHT — {truncate_payload(decoded)}")
            else:
                print(
                    f"msgbinary #{msg_id}: ❌ WRONG — length: {truncate_payload(payload_display)} | Reason: {reason}")

    conn.close()


# --- Entry point for the script ---
if __name__ == '__main__':
    main()

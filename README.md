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

## Setup

1. **Install Python 3.10+**
2. **Clone the repo**

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd aetheric-engine-client


"""Serve one SQLite value so a real browser can verify the test environment."""
import json
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

db = sqlite3.connect(sys.argv[1])
db.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER PRIMARY KEY)")
db.execute("INSERT OR IGNORE INTO probe VALUES (1)")
db.commit()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        row = db.execute("SELECT id FROM probe").fetchone()
        body = json.dumps({"value": row[0]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


server = HTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()

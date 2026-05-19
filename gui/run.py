#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui.app import create_app

app, socketio = create_app()

if __name__ == "__main__":
    print("Open Duck Mini Dashboard")
    print("Open http://localhost:5000 in your browser")
    socketio.run(app, host="0.0.0.0", port=5001, debug=False)

import webbrowser
import time
import threading
from app import app, init_db

def open_browser():
    # wait a bit for server to start
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    init_db()
    
    # open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("Starting Community Contribution Tracking System...")
    print("Opening browser at http://127.0.0.1:5000")
    print("Press Ctrl+C to quit")
    
    app.run(debug=True, port=5000, use_reloader=True)

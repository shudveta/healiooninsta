import time
import requests
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from instagrapi import Client

# Configs
GEMINI_API_URL = "https://yabbering-jenifer-shudveta-it-solutions-38e150de.koyeb.app/dr_healio_chat"
INSTA_USERNAME = os.getenv("INSTA_USERNAME", "ipdnow")
INSTA_PASSWORD = os.getenv("INSTA_PASSWORD", "@Dhruvi&Raghav2006")
SESSION_FILE = "session.json"

# Initialize
cl = Client()

def load_session():
    """Load session from file if it exists"""
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            print(f"✅ Session loaded from {SESSION_FILE}")
            return True
        except Exception as e:
            print(f"⚠️ Error loading session: {e}")
            return False
    return False

def save_session():
    """Save current session to file"""
    try:
        cl.dump_settings(SESSION_FILE)
        print(f"✅ Session saved to {SESSION_FILE}")
    except Exception as e:
        print(f"⚠️ Error saving session: {e}")

def login_with_fallback():
    """Try to load session, fallback to username/password login"""
    # First try to load existing session
    if load_session():
        try:
            # Verify session is still valid
            cl.get_timeline_feed()
            print(f"✅ Session is valid, logged in as {INSTA_USERNAME}")
            return True
        except Exception as e:
            print(f"⚠️ Session expired: {e}")
    
    # Fallback to username/password login
    try:
        print(f"🔄 Logging in with username/password...")
        
        # Add delay and user agent for better success rate
        cl.delay_range = [1, 3]
        cl.set_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15")
        
        # Try login with timeout
        import signal
        def timeout_handler(signum, frame):
            raise TimeoutError("Login timeout")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)  # 60 second timeout
        
        try:
            cl.login(INSTA_USERNAME, INSTA_PASSWORD)
            signal.alarm(0)  # Cancel timeout
            print(f"✅ Logged in as {INSTA_USERNAME}")
            save_session()
            return True
        except TimeoutError:
            signal.alarm(0)
            print(f"❌ Login timeout - Instagram might be requiring verification")
            return False
            
    except Exception as e:
        print(f"❌ Login failed: {e}")
        print(f"❌ Error details: {str(e)}")
        return False

# Track messages
last_message_ids = {}
history_map = {}

def get_reply_from_endpoint(user_id, user_input):
    # Get history in the old format (dict format)
    history_dict = history_map.get(user_id, [])
    
    # Convert history to the format your API expects: [["user_msg", "bot_response"], ...]
    history_pairs = []
    for i in range(0, len(history_dict), 2):
        if i + 1 < len(history_dict):
            user_msg = history_dict[i].get("text", "")
            bot_msg = history_dict[i + 1].get("text", "")
            history_pairs.append([user_msg, bot_msg])
    
    payload = {
        "user_input": user_input,
        "history": history_pairs  # Send as list of pairs
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "response" in data and data["response"]:
            # Store in dict format for internal use
            history_dict.append({"role": "user", "text": user_input})
            history_dict.append({"role": "bot", "text": data["response"]})
            history_map[user_id] = history_dict[-20:]  # limit history to last 20 (10 pairs)
            return data["response"]
        else:
            print(f"⚠️ Empty or invalid response from API: {data}")
            return "⚠️ Sorry, I didn't get that. Please try again."
    except requests.exceptions.Timeout:
        print(f"❌ Gemini endpoint timeout")
        return "⚠️ I'm taking longer than usual to respond. Please try again."
    except requests.exceptions.RequestException as e:
        print(f"❌ Gemini endpoint error: {e}")
        return "⚠️ Dr. Healio is currently busy. Try again later."
    except Exception as e:
        print(f"❌ Unexpected error in get_reply_from_endpoint: {e}")
        return "⚠️ Something went wrong. Please try again."

# Health check server for Koyeb
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            status = {
                "status": "healthy",
                "bot": "running",
                "logged_in": bool(cl and hasattr(cl, 'user_id') and cl.user_id),
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(status).encode())
        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass

def start_health_server():
    """Start health check server in background thread"""
    server = HTTPServer(('0.0.0.0', 8000), HealthCheckHandler)
    print("🏥 Health check server started on port 8000")
    server.serve_forever()

def main():
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Login with session fallback
    if not login_with_fallback():
        print("❌ Failed to login. Exiting...")
        return
    
    print("🤖 Bot started. Monitoring messages...")
    
    while True:
        try:
            inbox = cl.direct_threads()
            for thread in inbox:
                try:
                    # Skip threads with no users
                    if not thread.users or len(thread.users) == 0:
                        continue
                        
                    # Get basic thread info
                    thread_id = thread.id
                    
                    # Get the last message
                    if not thread.messages or len(thread.messages) == 0:
                        continue
                        
                    msg = thread.messages[0]
                    
                    # Get the bot's user ID for comparison
                    bot_user_id = cl.user_id
                    
                    # Skip messages from the bot itself - simplified check
                    if str(msg.user_id) == str(bot_user_id):
                        continue
                    
                    # Avoid responding to messages already replied
                    if msg.id == last_message_ids.get(thread_id):
                        continue
                    last_message_ids[thread_id] = msg.id

                    # Skip if it's a system event or story reply or empty message
                    if not msg.text or not msg.text.strip():
                        continue

                    # Find the user who sent the message (simplified)
                    sender_username = "Unknown"
                    user_id = None
                    
                    # Try to get user from thread participants
                    if thread.users:
                        # For 1-on-1 chats, get the other user (not the bot)
                        for user in thread.users:
                            if str(user.pk) != str(bot_user_id):
                                user_id = user.pk
                                sender_username = user.username
                                break
                    
                    # If we still don't have a user_id, use the message sender
                    if not user_id:
                        user_id = msg.user_id
                    
                    if not user_id:
                        continue

                    print(f"📩 New message from @{sender_username}: {msg.text}")

                    reply = get_reply_from_endpoint(user_id, msg.text.strip())
                    print(f"🤖 Bot reply: {reply}")
                    
                    try:
                        cl.direct_send(reply, [user_id])
                        print(f"✅ Reply sent successfully to @{sender_username}")
                    except Exception as e:
                        print(f"❌ Error sending reply: {e}")
                        
                except Exception as e:
                    print(f"❌ Error processing thread {thread.id if hasattr(thread, 'id') else 'unknown'}: {e}")
                    continue
                    
            time.sleep(10)

        except KeyboardInterrupt:
            print("\n🛑 Bot stopped.")
            break
        except Exception as e:
            print(f"❌ General Error: {e}")
            print(f"❌ Error type: {type(e).__name__}")
            # Save session before continuing
            save_session()
            time.sleep(10)

if __name__ == "__main__":
    main()

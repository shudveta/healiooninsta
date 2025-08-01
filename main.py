import time
import requests
from fastapi import FastAPI
from instagrapi import Client
from threading import Lock

app = FastAPI()
mutex = Lock()

# Configs
GEMINI_API_URL = "https://yabbering-jenifer-shudveta-it-solutions-38e150de.koyeb.app/dr_healio_chat"
INSTA_USERNAME = "ipdnow"
INSTA_PASSWORD = "@Dhruvi&Raghav2006"

# Initialize
cl = Client()
cl.load_settings("session.json")
print(f"✅ Logged in as {INSTA_USERNAME}")

try:
    cl.get_timeline_feed()  # Light call to check if session is valid
except Exception:
    print("Session expired or invalid, please re-login.")
    raise

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

@app.get("/ping")
def check_and_reply():
    with mutex:
        try:
            inbox = cl.direct_threads()
            for thread in inbox:
                try:
                    if not thread.users or len(thread.users) == 0:
                        continue
                    
                    thread_id = thread.id
                    
                    if not thread.messages or len(thread.messages) == 0:
                        continue
                    
                    msg = thread.messages[0]
                    bot_user_id = cl.user_id
                    
                    if str(msg.user_id) == str(bot_user_id):
                        continue
                    
                    if msg.id == last_message_ids.get(thread_id):
                        continue
                    last_message_ids[thread_id] = msg.id

                    if not msg.text or not msg.text.strip():
                        continue

                    sender_username = "Unknown"
                    user_id = None
                    
                    if thread.users:
                        for user in thread.users:
                            if str(user.pk) != str(bot_user_id):
                                user_id = user.pk
                                sender_username = user.username
                                break
                    
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
                    
            return {"status": "success", "message": "Ping processed"}

        except Exception as e:
            print(f"❌ General Error: {e}")
            print(f"❌ Error type: {type(e).__name__}")
            return {"status": "error", "details": str(e)}

import requests
import tomllib
import tomli_w
from pathlib import Path


config_path = Path(__file__).resolve().parent / "config.toml"
with open(config_path, 'rb') as config_file:
    config = tomllib.load(config_file)

BOT_TOKEN = config['bot_token']
CHAT_ID = config['chat_id']


url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"


response = requests.get(url)
updates = response.json()

if updates["ok"]:
    topics = {}
    
    
    for update in updates["result"]:
        if "message" in update and "message_thread_id" in update["message"] and "reply_to_message" in update["message"]:
            
            topic_id = update["message"]["message_thread_id"]
            topic_name = update["message"]["reply_to_message"]["forum_topic_created"]["name"]  
            
            # Store the topic name and thread ID in a dictionary
            if topic_name not in topics or topics.get(topic_name) != topic_id:
                topics[topic_name] = topic_id
                print(f"Found topic '{topic_name}' with Thread ID: {topic_id}")

   
    if topics:
        
        config.setdefault("topics",{}).update(topics)
        with open(config_path, "wb") as config_file:
            tomli_w.dump(config, config_file)

        print("Topics saved to config.toml")
    else:
        print("There are no topics to save in the config.")
else:
    print("Failed to fetch updates:", updates)

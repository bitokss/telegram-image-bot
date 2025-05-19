# 📤 Telegram Image Sender Bot

This bot sends images to specific **topics (threads)** in a **Telegram group** using the Bot API.

---

## 🚀 Getting Started

### 1. Add and Configure the Bot in Your Telegram Group

* **Step 1:** Add your bot to your desired **Telegram group**.
* **Step 2:** Promote the bot to **Administrator** with permission to:

  * Send messages
  * Read all messages

---

### 2. Prepare the Config File

Edit the `config.toml` file with the following required settings:

```toml
bot_token = "YOUR_BOT_TOKEN"
chat_id = "@your_group_username_or_chat_id"

folder_path = "path_to_image_folder"
max_retries = 3
timeout = 20
time_between_retries = 3

resize_max_dimension = 4096
resize_min_dimension = 320

allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp"]

[topics]
# This section will be filled automatically after running `get_topics.py`
```

📁 In the `folder_path` directory:

* Create **one folder per topic**
* Place relevant images inside each corresponding folder

Example structure:

```
images/
📄 topic1/
    image1.jpg
    image2.jpg
📄 topic2/
    image3.jpg
    image4.jpg
```

---

### 3. Map Group Topics to Thread IDs

Run the following script after sending **an initial message** in each group topic:

```bash
python3 get_topics.py
```

This script:

* Calls Telegram's `getUpdates` endpoint
* Finds topic names and thread IDs
* Updates the `[topics]` section in your `config.toml`

---

### 4. Run the Bot

Once the config is ready and topics are mapped:

```bash
python3 main.py
```

The bot will:

* Resize images if needed
* Send each image as both **photo** and **document** to its corresponding topic
* Retry failed messages (based on config)

---

## 🛠 Dependencies

Install dependencies using `pip`:

```bash
pip install -r requirements.txt
```

---

## 📌 Notes

* Only `.jpg`, `.png`, `.gif`, `.bmp`, and `.jpeg` are supported.
* Images are resized based on `resize_max_dimension` and `resize_min_dimension` before sending..

---

## 📄 License

MIT License

---

## 🤖 Created By

A Telegram automation enthusiast — powered by Python 🐍


import asyncio
import tomllib
import logging
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError, NetworkError, TimedOut
from PIL import Image
import io
import os

# -----------------------------
# Configuration
# -----------------------------
CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
LOG_PATH = Path(__file__).resolve().parent / "bot.log"

with open(CONFIG_PATH, 'rb') as config_file:
    config = tomllib.load(config_file)

# -----------------------------
# Logging Configuration
# -----------------------------
logger = logging.getLogger("telegram_bot")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_PATH)
console_handler = logging.StreamHandler()
file_handler.setLevel(logging.ERROR)
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# -----------------------------
# Load Config Values
# -----------------------------
BOT_TOKEN = config['bot_token']
CHAT_ID = config['chat_id']
FOLDER_PATH = Path(config['folder_path'])
MAX_RETRIES = config['max_retries']
TIMEOUT = config['timeout']
TIME_BETWEEN_RETRIES = config['time_between_retries']
RESIZE_MAX = config['resize_max_dimension']
RESIZE_MIN = config['resize_min_dimension']
TOPICS = config.get('topics', {})
ALLOWED_EXTENSIONS = set(config['allowed_extensions'])

# Initialize Telegram Bot
bot = Bot(token=BOT_TOKEN)

# -----------------------------
# Utility Functions
# -----------------------------
def is_image(file_path: Path) -> bool:
    """Check if the file has an allowed image extension."""
    return file_path.suffix.lower() in ALLOWED_EXTENSIONS

def resize_photo(photo_path: Path) -> io.BytesIO:
    """Resize photo based on config and return as in-memory JPEG."""
    with Image.open(photo_path) as img:
        width, height = img.size

        if max(width, height) > RESIZE_MAX:
            ratio = RESIZE_MAX / max(width, height)
            new_size = (int(width * ratio), int(height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        elif min(width, height) < RESIZE_MIN:
            new_size = (RESIZE_MIN, RESIZE_MIN)
            img = img.resize(new_size, Image.LANCZOS)

        byte_arr = io.BytesIO()
        img.save(byte_arr, format='JPEG')
        byte_arr.seek(0)
        return byte_arr

async def send_with_retries(send_func, *args, max_retries=MAX_RETRIES, **kwargs):
    """Attempt to send a message with retries on timeout/network errors."""
    for attempt in range(max_retries):
        try:
            await send_func(*args, **kwargs)
            return
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Retry {attempt+1}/{max_retries} due to network error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(TIME_BETWEEN_RETRIES)
            else:
                logger.error("Max retries reached. Giving up.")
                raise
        except TelegramError as e:
            logger.error(f"Telegram API error: {e}")
            raise

# -----------------------------
# Main Process Function
# -----------------------------
async def process_folder(folder_name: str):
    folder_path = FOLDER_PATH / folder_name
    logger.info(f"Processing folder: {folder_name}")

    for file_path in folder_path.iterdir():
        if not file_path.is_file() or not is_image(file_path):
            continue

        try:
            # Send as photo
            with resize_photo(file_path) as photo:
                logger.info(f"Sending {file_path.name} as photo...")
                await send_with_retries(
                    bot.send_photo,
                    chat_id=CHAT_ID,
                    photo=photo,
                    read_timeout=TIMEOUT,
                    write_timeout=TIMEOUT,
                    message_thread_id=TOPICS.get(folder_name)
                )

            # Send as document
            with open(file_path, 'rb') as doc:
                logger.info(f"Sending {file_path.name} as document...")
                await send_with_retries(
                    bot.send_document,
                    chat_id=CHAT_ID,
                    document=doc,
                    read_timeout=TIMEOUT,
                    write_timeout=TIMEOUT,
                    message_thread_id=TOPICS.get(folder_name)
                )

        except TelegramError as e:
            logger.error(f"Failed to send {file_path.name}: {e}")

    logger.info(f"Finished processing folder: {folder_name}")

# -----------------------------
# Entry Point
# -----------------------------
if __name__ == '__main__':
    folder_names = [f.name for f in FOLDER_PATH.iterdir() if f.is_dir()]
    asyncio.run(asyncio.gather(*(process_folder(folder) for folder in folder_names)))

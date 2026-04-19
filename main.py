import asyncio
import tomllib
import logging
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError, NetworkError, TimedOut
from PIL import Image
import io


class ImageTracker:
    """Handles tracking of sent and failed images per chat."""
    
    def __init__(self, groups_dir: Path):
        self.groups_dir = groups_dir
        self.groups_dir.mkdir(exist_ok=True)
    
    def get_log_file(self, chat_id: str) -> Path:
        """Get log file path for a specific chat."""
        return self.groups_dir / f"{chat_id}.log"
    
    def read_log(self, chat_id: str) -> tuple[set, set]:
        """Read successful and unsuccessful images from log file."""
        log_file = self.get_log_file(chat_id)
        successful = set()
        unsuccessful = set()
        
        if not log_file.exists():
            return successful, unsuccessful
        
        try:
            with open(log_file, 'r') as f:
                content = f.read().strip()
                
            if not content:
                return successful, unsuccessful
            
            sections = content.split('unsuccessful_images_sent:')
            
            # Parse successful images
            if sections[0].strip():
                successful_section = sections[0].replace('successful_images_sent:', '').strip()
                if successful_section:
                    successful = set(line.strip() for line in successful_section.split('\n') if line.strip())
            
            # Parse unsuccessful images
            if len(sections) > 1 and sections[1].strip():
                unsuccessful = set(line.strip() for line in sections[1].split('\n') if line.strip())
            
        except Exception as e:
            logging.error(f"Error reading log file {log_file}: {e}")
        
        return successful, unsuccessful
    
    def write_log(self, chat_id: str, successful: set, unsuccessful: set):
        """Write successful and unsuccessful images to log file."""
        log_file = self.get_log_file(chat_id)
        
        try:
            with open(log_file, 'w') as f:
                f.write("successful_images_sent:\n")
                for img in sorted(successful):
                    f.write(f"{img}\n")
                
                f.write("\nunsuccessful_images_sent:\n")
                for img in sorted(unsuccessful):
                    f.write(f"{img}\n")
        except Exception as e:
            logging.error(f"Error writing log file {log_file}: {e}")
    
    def add_successful(self, chat_id: str, image_name: str):
        """Add image to successful list and remove from unsuccessful."""
        successful, unsuccessful = self.read_log(chat_id)
        successful.add(image_name)
        unsuccessful.discard(image_name)
        self.write_log(chat_id, successful, unsuccessful)
    
    def add_unsuccessful(self, chat_id: str, image_name: str):
        """Add image to unsuccessful list."""
        successful, unsuccessful = self.read_log(chat_id)
        if image_name not in successful:
            unsuccessful.add(image_name)
            self.write_log(chat_id, successful, unsuccessful)
    
    def get_unsent_images(self, chat_id: str, all_images: list) -> list:
        """Get list of images that haven't been successfully sent."""
        successful, _ = self.read_log(chat_id)
        
        # Filter out images that are already successfully sent
        unsent_images = []
        skipped_count = 0
        
        for img in all_images:
            if img.name in successful:
                logging.debug(f"SKIPPING {img.name} - already in successful_images_sent")
                skipped_count += 1
            else:
                unsent_images.append(img)
        
        if skipped_count > 0:
            logging.info(f"Skipped {skipped_count} already sent images for chat {chat_id}")
        
        return unsent_images
    
    def get_unsuccessful_images(self, chat_id: str) -> set:
        """Get set of unsuccessful images."""
        _, unsuccessful = self.read_log(chat_id)
        return unsuccessful
    
    def is_image_already_sent(self, chat_id: str, image_name: str) -> bool:
        """Check if an image has already been successfully sent."""
        successful, _ = self.read_log(chat_id)
        return image_name in successful


class TelegramImageBot:
    """Main bot class for sending images to Telegram."""
    
    def __init__(self, config_path: Path):
        self.config = self._load_config(config_path)
        self.bot = Bot(token=self.config['bot_token'])
        self.tracker = ImageTracker(Path(__file__).resolve().parent / "groups")
        self._setup_logging()
    
    def _load_config(self, config_path: Path) -> dict:
        """Load configuration from TOML file."""
        with open(config_path, 'rb') as f:
            return tomllib.load(f)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_path = Path(__file__).resolve().parent / "bot.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
        )
        
        logging.getLogger().handlers[0].setLevel(logging.ERROR)
        logging.getLogger().handlers[1].setLevel(logging.INFO)
    
    def _is_image(self, file_path: Path) -> bool:
        """Check if file has allowed image extension."""
        allowed_extensions = set(self.config['allowed_extensions'])
        return file_path.suffix.lower() in allowed_extensions
    
    def _resize_photo(self, photo_path: Path) -> io.BytesIO:
        """Resize photo based on config and return as in-memory JPEG."""
        with Image.open(photo_path) as img:
            width, height = img.size
            resize_max = self.config['resize_max_dimension']
            resize_min = self.config['resize_min_dimension']
            
            if max(width, height) > resize_max:
                ratio = resize_max / max(width, height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            elif min(width, height) < resize_min:
                new_size = (resize_min, resize_min)
                img = img.resize(new_size, Image.LANCZOS)
            
            byte_arr = io.BytesIO()
            img.save(byte_arr, format='JPEG')
            byte_arr.seek(0)
            return byte_arr
    
    async def _send_with_retries(self, send_func, *args, **kwargs):
        """Send message with retry logic for network errors."""
        max_retries = self.config['max_retries']
        retry_delay = self.config['time_between_retries']
        
        for attempt in range(max_retries):
            try:
                await send_func(*args, **kwargs)
                return True
            except (TimedOut, NetworkError) as e:
                logging.warning(f"Retry {attempt+1}/{max_retries} due to network error: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logging.error("Max retries reached. Giving up.")
                    return False
            except TelegramError as e:
                logging.error(f"Telegram API error: {e}")
                return False
    
    async def _send_image(self, file_path: Path, chat_id: str, folder_name: str) -> bool:
        """Send single image as both photo and document."""
        timeout = self.config['timeout']
        topics = self.config.get('topics', {})
        thread_id = topics.get(folder_name)
        
        try:
            # Send as photo
            with self._resize_photo(file_path) as photo:
                logging.info(f"Sending {file_path.name} as photo...")
                success = await self._send_with_retries(
                    self.bot.send_photo,
                    chat_id=chat_id,
                    photo=photo,
                    read_timeout=timeout,
                    write_timeout=timeout,
                    message_thread_id=thread_id
                )
                if not success:
                    return False
            
            # Send as document
            with open(file_path, 'rb') as doc:
                logging.info(f"Sending {file_path.name} as document...")
                success = await self._send_with_retries(
                    self.bot.send_document,
                    chat_id=chat_id,
                    document=doc,
                    read_timeout=timeout,
                    write_timeout=timeout,
                    message_thread_id=thread_id
                )
                return success
        
        except Exception as e:
            logging.error(f"Error sending {file_path.name}: {e}")
            return False
    
    def _get_folder_images(self, folder_path: Path) -> list:
        """Get all image files from folder."""
        return [f for f in folder_path.iterdir() if f.is_file() and self._is_image(f)]
    
    async def process_folder(self, folder_name: str):
        """Process all unsent images in a folder."""
        folder_path = Path(self.config['folder_path']) / folder_name
        chat_id = self.config['chat_id']
        
        if not folder_path.exists():
            logging.warning(f"Folder {folder_path} does not exist")
            return
        
        logging.info(f"Processing folder: {folder_name}")
        
        all_images = self._get_folder_images(folder_path)
        logging.info(f"Found {len(all_images)} total images in {folder_name}")
        
        # Get only images that haven't been successfully sent
        unsent_images = self.tracker.get_unsent_images(chat_id, all_images)
        
        if len(unsent_images) == 0:
            logging.info(f"All images in {folder_name} have already been sent successfully")
            return
        
        logging.info(f"Found {len(unsent_images)} unsent images in {folder_name}")
        
        for image_path in unsent_images:
            # CRITICAL CHECK: Ensure image hasn't been sent since we loaded the list
            if self.tracker.is_image_already_sent(chat_id, image_path.name):
                logging.info(f"SKIP: {image_path.name} - already in successful_images_sent")
                continue
            
            logging.info(f"SENDING: {image_path.name} - not in successful_images_sent")
            success = await self._send_image(image_path, chat_id, folder_name)
            
            if success:
                self.tracker.add_successful(chat_id, image_path.name)
                logging.info(f"✅ SUCCESS: Added {image_path.name} to successful_images_sent")
            else:
                self.tracker.add_unsuccessful(chat_id, image_path.name)
                logging.error(f"❌ FAILED: Added {image_path.name} to unsuccessful_images_sent")
        
        logging.info(f"Finished processing folder: {folder_name}")
    
    async def unsuccessful_image_resend(self):
        """Resend all unsuccessful images for the configured chat."""
        chat_id = self.config['chat_id']
        folder_path = Path(self.config['folder_path'])
        
        unsuccessful_names = self.tracker.get_unsuccessful_images(chat_id)
        
        if not unsuccessful_names:
            logging.info("No unsuccessful images to resend")
            return
        
        logging.info(f"Attempting to resend {len(unsuccessful_names)} unsuccessful images")
        
        # Find unsuccessful images in all folders
        for folder in folder_path.iterdir():
            if not folder.is_dir():
                continue
            
            for image_path in self._get_folder_images(folder):
                if image_path.name in unsuccessful_names:
                    # CRITICAL CHECK: Don't resend if image is now in successful list
                    if self.tracker.is_image_already_sent(chat_id, image_path.name):
                        logging.info(f"SKIP RESEND: {image_path.name} - now in successful_images_sent")
                        continue
                    
                    logging.info(f"RESENDING: {image_path.name} from unsuccessful list")
                    success = await self._send_image(image_path, chat_id, folder.name)
                    
                    if success:
                        self.tracker.add_successful(chat_id, image_path.name)
                        logging.info(f"✅ RESEND SUCCESS: {image_path.name}")
                    else:
                        logging.error(f"❌ RESEND FAILED: {image_path.name}")
    
    async def run(self):
        """Run the bot to process all folders."""
        folder_path = Path(self.config['folder_path'])
        folder_names = [f.name for f in folder_path.iterdir() if f.is_dir()]
        
        if not folder_names:
            logging.warning("No folders found to process")
            return
        
        await asyncio.gather(*(self.process_folder(folder) for folder in folder_names))


# -----------------------------
# Entry Point
# -----------------------------
async def main():
    """Main entry point."""
    config_path = Path(__file__).resolve().parent / "config.toml"
    bot = TelegramImageBot(config_path)
    await bot.run()


async def resend_unsuccessful():
    """Entry point for resending unsuccessful images."""
    config_path = Path(__file__).resolve().parent / "config.toml"
    bot = TelegramImageBot(config_path)
    await bot.unsuccessful_image_resend()


if __name__ == '__main__':
    asyncio.run(main()) 
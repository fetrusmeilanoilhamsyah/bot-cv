import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN     = os.getenv("BOT_TOKEN")
ADMIN_IDS     = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@admin")
GROUP_LINK    = os.getenv("GROUP_LINK", "https://t.me/grup")
HARGA_MEMBER  = os.getenv("HARGA_MEMBER", "Hubungi admin")

TMP_DIR       = os.path.join(os.path.dirname(__file__), "tmp", "sessions")

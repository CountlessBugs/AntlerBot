from dotenv import load_dotenv
load_dotenv()

import os
os.environ.setdefault("NCATBOT_CONFIG_PATH", "config/ncatbot.yaml")

from ncatbot.core import BotClient
from src.core.message_handler import register

bot = BotClient()
register(bot)
bot.run()

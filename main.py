from dotenv import load_dotenv
load_dotenv()

import os
os.environ.setdefault("NCATBOT_CONFIG_PATH", "config/ncatbot.yaml")

from ncatbot.core import BotClient
from src.messaging import handlers as message_handlers
from src.runtime import scheduled_tasks

bot = BotClient()
message_handlers.register(bot)

@bot.on_startup()
async def on_startup(event):
    await scheduled_tasks.register(bot)

bot.run()

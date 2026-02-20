from dotenv import load_dotenv
load_dotenv()

import os
os.environ.setdefault("NCATBOT_CONFIG_PATH", "config/ncatbot.yaml")

from ncatbot.core import BotClient, PrivateMessage

bot = BotClient()

@bot.private_event()
async def on_private_message(msg: PrivateMessage):
    if msg.raw_message == "测试":
        await bot.api.post_private_msg(msg.user_id, text="NcatBot 测试成功喵~")

bot.run()

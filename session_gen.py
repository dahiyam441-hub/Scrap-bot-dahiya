"""Generate a Telethon StringSession locally. Never paste it into chat or GitHub."""
import asyncio,os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
load_dotenv()
async def main():
    api_id=int(os.environ['API_ID']); api_hash=os.environ['API_HASH']
    client=TelegramClient(StringSession(),api_id,api_hash)
    await client.start()
    print('\nTELETHON_SESSION (copy directly into your hosting secret; do not share):\n')
    print(client.session.save())
    await client.disconnect()
if __name__=='__main__': asyncio.run(main())

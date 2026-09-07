# -*- coding: utf-8 -*-
"""Локальный вход в Telegram через SOCKS5 127.0.0.1:10808. 2 шага.
  python tg_login.py send   +7XXXXXXXXXX
  python tg_login.py code   12345           # + опц. 2FA: python tg_login.py code 12345 mypass
Сессия: sf_session.session (в этой папке). Креды из локального .env (app sendfiles)."""
import os,io,sys,json,asyncio
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
from dotenv import load_dotenv
from telethon import TelegramClient
load_dotenv(r"C:\Users\Yuri\PycharmProjects\PythonProject\idea-eexpo-2026\.env")
API_ID=int(os.getenv("TELEGRAM_API_ID")); API_HASH=os.getenv("TELEGRAM_API_HASH")
PROXY=('socks5','127.0.0.1',10808); ST="tg_login_state.json"; SESSION="sf_session"
async def main():
    act=sys.argv[1]
    cl=TelegramClient(SESSION,API_ID,API_HASH,proxy=PROXY)
    await cl.connect()
    if act=="send":
        phone=sys.argv[2]
        sent=await cl.send_code_request(phone)
        json.dump({"phone":phone,"hash":sent.phone_code_hash},open(ST,"w"))
        print("CODE_SENT:", type(sent.type).__name__)
    elif act=="code":
        s=json.load(open(ST)); code=sys.argv[2]
        from telethon.errors import SessionPasswordNeededError
        try:
            await cl.sign_in(s["phone"], code, phone_code_hash=s["hash"])
        except SessionPasswordNeededError:
            if len(sys.argv)>3:
                await cl.sign_in(password=sys.argv[3])
            else:
                print("NEED_2FA: повтори: python tg_login.py code <код> <пароль2FA>"); await cl.disconnect(); return
        me=await cl.get_me()
        print("ВОШЛИ:", me.first_name, "@"+(me.username or ""), "id", me.id)
    await cl.disconnect()
asyncio.run(main())

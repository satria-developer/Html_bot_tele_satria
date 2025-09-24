#!/usr/bin/env python3
# bot_gethtml.py
# Bot Telegram ambil HTML dari web
# Dibuat oleh satria-developer

import asyncio
import socket
import ipaddress
from io import BytesIO
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ====== MASUKKAN TOKEN BOT KAMU DI SINI ======
BOT_TOKEN = "ISI TOKEN BOT"   # ganti dengan token dari @BotFather

MAX_INLINE_CHARS = 3800    # batas agar pesan tidak terlalu panjang
MAX_DOWNLOAD_BYTES = 200_000  # 200 KB max untuk ambil HTML


# Cek host apakah private (hindari SSRF)
async def is_host_private(host: str) -> bool:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, host, None)
    except Exception:
        return True
    for entry in infos:
        sockaddr = entry[4]
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                return True
        except Exception:
            continue
    return False


# Normalisasi URL
def normalize_target(target: str) -> str:
    target = target.strip()
    if target.startswith("view-source:"):
        target = target[len("view-source:"):]
    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target
    return target


# Ambil HTML dengan batas
async def fetch_html_limited(url: str, max_bytes: int):
    timeout = aiohttp.ClientTimeout(total=25)
    headers = {"User-Agent": "Telegram-GetHTML-Bot/1.0 (+satria-developer)"}
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(url, headers=headers, allow_redirects=True) as resp:
            status = resp.status
            buf = BytesIO()
            total = 0
            async for chunk in resp.content.iter_chunked(10240):
                buf.write(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            return buf.getvalue(), {"status": status, "truncated": total >= max_bytes}


# Command: /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo saya dibuat oleh satria-developer gunakan /gethtml untuk mengambil html dari web lain!")


# Command: /gethtml
async def gethtml_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Gunakan: /gethtml (https://namaweb.com")
        return

    target_raw = " ".join(context.args).strip()
    target = normalize_target(target_raw)

    try:
        parsed = urlparse(target)
        host = parsed.hostname
        if not host:
            await update.message.reply_text("URL tidak valid.")
            return
    except Exception:
        await update.message.reply_text("URL tidak valid.")
        return

    await update.message.reply_text(f"Sedang mengambil HTML dari: {target}")

    # Cek private host
    if await is_host_private(host):
        await update.message.reply_text("Dilarang: host berada di jaringan privat/loopback.")
        return

    try:
        content_bytes, meta = await fetch_html_limited(target, MAX_DOWNLOAD_BYTES)
    except Exception as e:
        await update.message.reply_text(f"Gagal mengambil konten: {e}")
        return

    truncated = meta.get("truncated", False)
    status = meta.get("status", "unknown")
    info_line = f"HTTP status: {status}. {'(terpotong)' if truncated else ''}"

    try:
        text = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        text = None

    if text and len(text) <= MAX_INLINE_CHARS:
        await update.message.reply_text(f"{info_line}\n\n{text}")
    else:
        filename = (host.replace(':', '_') + ".html")[:100]
        bio = BytesIO()
        if text:
            bio.write(text.encode("utf-8"))
        else:
            bio.write(content_bytes)
        bio.seek(0)
        await update.message.reply_document(document=bio, filename=filename, caption=info_line)


def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456"):
        print("❌ Ganti BOT_TOKEN dulu dengan token asli dari @BotFather!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("gethtml", gethtml_command))

    print("✅ Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
    

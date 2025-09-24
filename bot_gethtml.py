#!/usr/bin/env python3
# bot_gethtml.py
import os
import asyncio
import socket
import ipaddress
from io import BytesIO
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Config
BOT_TOKEN = os.environ.get("8449038235:AAHDRaYA_hlgNQGlI4zfC3WLf5s4saXHkWQ")  # atur BOT_TOKEN di env
MAX_INLINE_CHARS = 3800   # batas isi pesan inline (agar aman < 4096)
MAX_DOWNLOAD_BYTES = 200_000  # batasi berapa banyak bytes yang diambil (200 KB)

# Helper: cek apakah host resolve ke IP privat/loopback
async def is_host_private(host: str) -> bool:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, socket.getaddrinfo, host, None)
    except Exception:
        return True  # bila tidak bisa resolve, treat as unsafe
    for entry in infos:
        sockaddr = entry[4]
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                return True
        except Exception:
            # jika parse ip gagal, skip
            continue
    return False

# Normalisasi input menjadi URL yang valid; menerima "view-source:..." per permintaan
def normalize_target(target: str) -> str:
    target = target.strip()
    if target.startswith("view-source:"):
        target = target[len("view-source:"):]
    # jika user hanya menulis contoh "namaweb.com", tambahkan https://
    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target
    return target

async def fetch_html(url: str) -> (bytes, dict):
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "User-Agent": "Telegram-GetHTML-Bot/1.0 (+satria-developer)"
    }
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(url, headers=headers, allow_redirects=True) as resp:
            # Baca hingga MAX_DOWNLOAD_BYTES
            content = await resp.content.readexactly(min(MAX_DOWNLOAD_BYTES, 65536)) if resp.content.at_eof() is False else await resp.read()
            # above logic is simple; we'll read up to limit by chunks if needed
            # safer approach below:
        # Reopen to actually read in chunks to limit — rewrite properly below

async def fetch_html_limited(url: str, max_bytes: int):
    timeout = aiohttp.ClientTimeout(total=25)
    headers = {"User-Agent": "Telegram-GetHTML-Bot/1.0 (+satria-developer)"}
    async with aiohttp.ClientSession(timeout=timeout) as sess:
        async with sess.get(url, headers=headers, allow_redirects=True) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            buf = BytesIO()
            total = 0
            async for chunk in resp.content.iter_chunked(10240):
                buf.write(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            return buf.getvalue(), {"status": status, "headers": resp_headers, "truncated": total >= max_bytes}

# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Halo saya dibuat oleh satria-developer")

async def gethtml_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args is None or len(context.args) == 0:
        await update.message.reply_text("Gunakan: /gethtml https://namaweb.com  — atau /gethtml (https://namaweb.com")
        return

    target_raw = " ".join(context.args).strip()
    target = normalize_target(target_raw)

    # parse host
    try:
        parsed = urlparse(target)
        host = parsed.hostname
        if not host:
            await update.message.reply_text("URL tidak valid. Contoh:(https://example.com")
            return
    except Exception:
        await update.message.reply_text("URL tidak valid.")
        return

    await update.message.reply_text(f"Memproses mengambil HTML dari: {target}")

    # Cek private IP / SSRF
    try:
        private = await is_host_private(host)
    except Exception:
        private = True
    if private:
        await update.message.reply_text("Gagal: target terdeteksi berada di jaringan privat/loopback atau tidak dapat di-resolve. Untuk keamanan bot tidak akan mengambil dari sini.")
        return

    # Ambil HTML dengan batas
    try:
        content_bytes, meta = await fetch_html_limited(target, MAX_DOWNLOAD_BYTES)
    except Exception as e:
        await update.message.reply_text(f"Gagal mengambil konten: {e}")
        return

    truncated = meta.get("truncated", False)
    status = meta.get("status", "unknown")
    info_line = f"HTTP status: {status}. {'(terpotong karena ukuran)' if truncated else ''}"

    try:
        text = content_bytes.decode('utf-8', errors='replace')
    except Exception:
        # fallback: kirim sebagai file
        text = None

    if text is not None and len(text) <= MAX_INLINE_CHARS:
        reply = f"{info_line}\n\n{text}"
        await update.message.reply_text(reply)
    else:
        # kirim sebagai file
        filename = (host.replace(":", "_") + ".html")[:100]
        bio = BytesIO()
        if text is None:
            bio.write(content_bytes)
        else:
            bio.write(text.encode('utf-8'))
        bio.seek(0)
        await update.message.reply_document(document=bio, filename=filename, caption=info_line)

def main():
    token = BOT_TOKEN
    if not token:
        print("ERROR: atur BOT_TOKEN di environment variable.")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("gethtml", gethtml_command))

    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
          

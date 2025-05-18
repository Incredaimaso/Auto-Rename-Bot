from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaDocument, Message
from PIL import Image
from datetime import datetime
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from helper.utils import humanbytes, convert
from helper.database import AshutoshGoswami24
from config import Config
import os
import time
import re
import subprocess
import asyncio

renaming_operations = {}

# Pattern Definitions
pattern1 = re.compile(r"S(\d+)(?:E|EP)(\d+)")
pattern2 = re.compile(r"S(\d+)\s*(?:E|EP|-\s*EP)(\d+)")
pattern3 = re.compile(r"(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)")
pattern3_2 = re.compile(r"(?:\s*-\s*(\d+)\s*)")
pattern4 = re.compile(r"S(\d+)[^\d]*(\d+)", re.IGNORECASE)
patternX = re.compile(r"(\d+)")

pattern5 = re.compile(r"\b(?:.*?(\d{3,4}[^\dp]*p).*?|.*?(\d{3,4}p))\b", re.IGNORECASE)
pattern6 = re.compile(r"[([<{]?\s*4k\s*[)\]>}]?", re.IGNORECASE)
pattern7 = re.compile(r"[([<{]?\s*2k\s*[)\]>}]?", re.IGNORECASE)
pattern8 = re.compile(r"[([<{]?\s*HdRip\s*[)\]>}]?|\bHdRip\b", re.IGNORECASE)
pattern9 = re.compile(r"[([<{]?\s*4kX264\s*[)\]>}]?", re.IGNORECASE)
pattern10 = re.compile(r"[([<{]?\s*4kx265\s*[)\]>}]?", re.IGNORECASE)


def extract_quality(filename):
    for pattern, label in [
        (pattern5, None), (pattern6, "4k"), (pattern7, "2k"), (pattern8, "HdRip"),
        (pattern9, "4kX264"), (pattern10, "4kx265")
    ]:
        match = re.search(pattern, filename)
        if match:
            return match.group(1) if not label else label
    return "Unknown"


def extract_episode_number(filename):
    for pattern in [pattern1, pattern2, pattern3, pattern3_2, pattern4, patternX]:
        match = re.search(pattern, filename)
        if match:
            return match.group(2) if pattern in [pattern1, pattern2, pattern4] else match.group(1)
    return None


def progress_for_pyrogram(current, total, message, start):
    now = time.time()
    diff = now - start
    if diff < 10 and current != total:
        return

    percentage = current * 100 / total
    speed = current / diff
    eta = (total - current) / speed if speed != 0 else 0

    bar_length = 25
    filled_length = int(bar_length * current // total)
    bar = "■" * filled_length + "□" * (bar_length - filled_length)

    progress_msg = (
        f"⭒ ݊ ֺProgress: |{bar}| {percentage:.2f}%\n"
        f"⭒ ݊ ֺSpeed: {humanbytes(speed)}/s\n"
        f"⭒ ݊ ֺSize: {humanbytes(current)} of {humanbytes(total)}\n"
        f"⭒ ݊ ֺETA: {convert(eta)}"
    )
    try:
        asyncio.create_task(message.edit(progress_msg))
    except Exception:
        pass


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    format_template = await AshutoshGoswami24.get_format_template(user_id)
    media_preference = await AshutoshGoswami24.get_media_preference(user_id)

    if not format_template:
        return await message.reply_text("Please set an auto rename format using /autorename")

    media_type, file_id, file_name = None, None, None
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        media_type = media_preference or "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{message.video.file_name}.mp4"
        media_type = media_preference or "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = f"{message.audio.file_name}.mp3"
        media_type = media_preference or "audio"
    else:
        return await message.reply_text("Unsupported file type")

    if file_id in renaming_operations and (datetime.now() - renaming_operations[file_id]).seconds < 10:
        return

    renaming_operations[file_id] = datetime.now()

    episode_number = extract_episode_number(file_name)
    if episode_number:
        format_template = format_template.replace("[episode]", f"EP{episode_number}", 1)
        format_template = format_template.replace("[quality]", extract_quality(file_name))

    file_extension = os.path.splitext(file_name)[1]
    renamed_file_name = f"{format_template}{file_extension}"
    renamed_file_path = f"downloads/{renamed_file_name}"
    metadata_file_path = f"Metadata/{renamed_file_name}"

    os.makedirs(os.path.dirname(renamed_file_path), exist_ok=True)
    os.makedirs(os.path.dirname(metadata_file_path), exist_ok=True)

    download_msg = await message.reply_text("Downloading the file...")

    try:
        path = await client.download_media(
            message,
            file_name=renamed_file_path,
            progress=progress_for_pyrogram,
            progress_args=("Download Started...", download_msg, time.time()),
        )
    except Exception as e:
        del renaming_operations[file_id]
        return await download_msg.edit(f"**Download Error:** {e}")

    await download_msg.edit("Renaming and Adding Metadata...")

    try:
        os.rename(path, renamed_file_path)
        path = renamed_file_path

        metadata_added = False
        if await AshutoshGoswami24.get_metadata(user_id):
            metadata = await AshutoshGoswami24.get_metadata_code(user_id)
            if metadata:
                cmd = (
                    f'ffmpeg -i "{renamed_file_path}" -map 0 -c:s copy -c:a copy -c:v copy '
                    f'-metadata title="{metadata}" -metadata author="{metadata}" '
                    f'-metadata:s:s title="{metadata}" -metadata:s:a title="{metadata}" '
                    f'-metadata:s:v title="{metadata}" "{metadata_file_path}"'
                )
                try:
                    process = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    _, stderr = await process.communicate()
                    if process.returncode == 0:
                        metadata_added = True
                        path = metadata_file_path
                    else:
                        return await download_msg.edit(f"**Metadata Error:**\n{stderr.decode()}")
                except Exception as e:
                    return await download_msg.edit(f"**Metadata Exception:**\n{str(e)}")

        if not metadata_added:
            path = renamed_file_path
            await download_msg.edit("Metadata addition failed. Uploading renamed file only.")

        upload_msg = await download_msg.edit("Uploading the file...")
        ph_path, c_thumb = None, await AshutoshGoswami24.get_thumbnail(message.chat.id)
        c_caption = await AshutoshGoswami24.get_caption(message.chat.id)

        caption = (
            c_caption.format(filename=renamed_file_name, filesize=humanbytes(message.document.file_size), duration=convert(0))
            if c_caption else f"**{renamed_file_name}**"
        )

        if c_thumb:
            ph_path = await client.download_media(c_thumb)
        elif media_type == "video" and message.video.thumbs:
            ph_path = await client.download_media(message.video.thumbs[0].file_id)

        if ph_path:
            img = Image.open(ph_path).convert("RGB")
            img = img.resize((320, 320))
            img.save(ph_path, "JPEG")

        try:
            if media_type == "document":
                await client.send_document(message.chat.id, document=path, thumb=ph_path, caption=caption,
                                           progress=progress_for_pyrogram, progress_args=("Upload Started...", upload_msg, time.time()))
            elif media_type == "video":
                await client.send_video(message.chat.id, video=path, caption=caption, thumb=ph_path, duration=0,
                                        progress=progress_for_pyrogram, progress_args=("Upload Started...", upload_msg, time.time()))
            elif media_type == "audio":
                await client.send_audio(message.chat.id, audio=path, caption=caption, thumb=ph_path, duration=0,
                                        progress=progress_for_pyrogram, progress_args=("Upload Started...", upload_msg, time.time()))
        except Exception as e:
            os.remove(path)
            if ph_path:
                os.remove(ph_path)
            return await upload_msg.edit(f"**Upload Error:** {e}")

    except Exception as e:
        await download_msg.edit(f"**Error:** {e}")

    finally:
        for p in [renamed_file_path, metadata_file_path, ph_path]:
            if p and os.path.exists(p):
                os.remove(p)
        del renaming_operations[file_id]

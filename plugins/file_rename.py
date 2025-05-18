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

PATTERNS = {
    # Season and episode patterns
    'season_ep': re.compile(r'S(\d+)[._\s]?(?:E|EP)(\d+)', re.IGNORECASE),
    
    # Clean resolution pattern - only common resolutions
    'resolution': re.compile(r'(?:2160|1080|720|480)p|4k', re.IGNORECASE),
    
    # Clean audio pattern
    'audio': re.compile(r'\b(?:DUB|SUB|DUAL(?:\s*AUDIO)?)\b', re.IGNORECASE)
}

def extract_file_info(filename):
    """Extract title, season, episode, resolution and audio information from filename."""
    info = {
        'title': '',
        'season': '1',
        'episode': '1',
        'resolution': '',
        'audio': ''
    }
    
    # Remove file extension
    filename = os.path.splitext(filename)[0]
    
    # Extract season and episode
    season_ep_match = PATTERNS['season_ep'].search(filename)
    if season_ep_match:
        info['season'] = season_ep_match.group(1)
        info['episode'] = season_ep_match.group(2)
        # Remove the matched part for cleaner title extraction
        filename = PATTERNS['season_ep'].sub('', filename)
    
    # Extract resolution
    resolution_match = PATTERNS['resolution'].search(filename)
    if resolution_match:
        res = resolution_match.group(0).upper()
        info['resolution'] = '4K' if res == '4K' else res
        filename = PATTERNS['resolution'].sub('', filename)
    
    # Extract audio type
    audio_match = PATTERNS['audio'].search(filename)
    if audio_match:
        audio_type = audio_match.group(0).upper()
        if 'DUAL' in audio_type:
            info['audio'] = 'dual'
        elif 'SUB' in audio_type:
            info['audio'] = 'sub'
        elif 'DUB' in audio_type:
            info['audio'] = 'dub'
        filename = PATTERNS['audio'].sub('', filename)
    
    # Clean remaining text as title
    info['title'] = re.sub(r'[._]', ' ', filename)
    info['title'] = re.sub(r'\s+', ' ', info['title'])
    info['title'] = info['title'].strip()
    
    return info

def format_episode_number(episode):
    """Format episode number with leading zeros."""
    try:
        return f"{int(episode):02d}"
    except ValueError:
        return episode

@Client.on_message(filters.private & filters.command("file"))
async def set_file_format(client, message):
    try:
        format_text = message.text.split("/file ", 1)[1]
        await AshutoshGoswami24.set_format_template(message.from_user.id, format_text)
        await message.reply_text("File format template set successfully! ✅")
    except IndexError:
        await message.reply_text(
            "Please provide a format template.\n\n"
            "Variables available:\n"
            "• {title} - for anime title\n"
            "• {season} - for anime season\n"
            "• {episode} - for anime episode\n"
            "• {resolution} - for video resolution\n"
            "• {audio} - audio type (sub/dub/dual)\n\n"
            "Example:\n`/file S{season}E{episode} {title} [{audio}] {resolution}`"
        )

async def format_filename(template, file_info):
    """Format filename according to template and extracted information."""
    result = template
    
    replacements = {
        '{title}': file_info['title'],
        '{season}': file_info['season'],
        '{episode}': format_episode_number(file_info['episode']),
        '{resolution}': file_info['resolution'],
        '{audio}': file_info['audio']
    }
    
    for key, value in replacements.items():
        result = result.replace(key, str(value))
    
    return result

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    format_template = await AshutoshGoswami24.get_format_template(user_id)
    media_preference = await AshutoshGoswami24.get_media_preference(user_id)
    extract_source = await AshutoshGoswami24.get_extract_source(user_id)
    
    if not format_template:
        return await message.reply_text("Please set a file format using /file command")
    
    # Determine which source to use for extraction
    if extract_source == 'caption' and message.caption:
        extract_text = message.caption
    else:
        extract_text = message.document.file_name if message.document else \
                      message.video.file_name if message.video else \
                      message.audio.file_name
    
    file_info = extract_file_info(extract_text)

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

    file_info = extract_file_info(file_name)
    new_name = await format_filename(format_template, file_info)

    file_extension = os.path.splitext(file_name)[1]
    renamed_file_name = f"{new_name}{file_extension}"
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
            progress_args=("⭒ ݊ ֺ Dᴏᴡɴʟᴏᴀᴅɪɴɢ Yᴏᴜʀ Fɪʟᴇ", download_msg, time.time()),
        )
    except Exception as e:
        del renaming_operations[file_id]
        return await download_msg.edit(f"**❌ Dᴏᴡɴʟᴏᴀᴅ Eʀʀᴏʀ:** {e}")

    await download_msg.edit("⭒ ݊ ֺ Pʀᴏᴄᴇssɪɴɢ Yᴏᴜʀ Fɪʟᴇ...")

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

        upload_msg = await download_msg.edit("⭒ ݊ ֺ Sᴛᴀʀᴛɪɴɢ Uᴘʟᴏᴀᴅ...")
        
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
                await client.send_document(
                    message.chat.id,
                    document=path,
                    thumb=ph_path,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=("⭒ ݊ ֺ Uᴘʟᴏᴀᴅɪɴɢ Yᴏᴜʀ Fɪʟᴇ", upload_msg, time.time())
                )
            elif media_type == "video":
                await client.send_video(
                    message.chat.id,
                    video=path,
                    caption=caption,
                    thumb=ph_path,
                    duration=0,
                    progress=progress_for_pyrogram,
                    progress_args=("⭒ ݊ ֺ Uᴘʟᴏᴀᴅɪɴɢ Yᴏᴜʀ Vɪᴅᴇᴏ", upload_msg, time.time())
                )
            elif media_type == "audio":
                await client.send_audio(
                    message.chat.id,
                    audio=path,
                    caption=caption,
                    thumb=ph_path,
                    duration=0,
                    progress=progress_for_pyrogram,
                    progress_args=("⭒ ݊ ֺ Uᴘʟᴏᴀᴅɪɴɢ Yᴏᴜʀ Aᴜᴅɪᴏ", upload_msg, time.time())
                )
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

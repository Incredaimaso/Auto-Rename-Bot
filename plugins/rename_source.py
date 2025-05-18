from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from helper.database import AshutoshGoswami24

SOURCE_TYPES = {
    'caption': 'Extract from Caption',
    'filename': 'Extract from Filename'
}

@Client.on_message(filters.private & filters.command("source"))
async def source_command(client, message):
    """Handle /source command to set extraction source"""
    user_id = message.from_user.id
    current_source = await AshutoshGoswami24.get_extract_source(user_id) or 'filename'
    
    # Create inline keyboard
    buttons = []
    for source_key, source_name in SOURCE_TYPES.items():
        status = "✅" if current_source == source_key else ""
        buttons.append(
            [InlineKeyboardButton(
                f"{source_name} {status}",
                callback_data=f"setsource_{source_key}"
            )]
        )
    
    await message.reply_text(
        "**📝 Select Source for Information Extraction**\n\n"
        "Choose where to extract file information from:\n"
        "• Caption: Uses file caption for extraction\n"
        "• Filename: Uses filename for extraction\n\n"
        f"Current Source: **{SOURCE_TYPES[current_source]}**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("^setsource_"))
async def source_callback(client, callback_query: CallbackQuery):
    source_type = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    # Update source preference in database
    await AshutoshGoswami24.set_extract_source(user_id, source_type)
    
    # Update inline keyboard
    buttons = []
    for source_key, source_name in SOURCE_TYPES.items():
        status = "✅" if source_type == source_key else ""
        buttons.append(
            [InlineKeyboardButton(
                f"{source_name} {status}",
                callback_data=f"setsource_{source_key}"
            )]
        )
    
    await callback_query.message.edit_text(
        "**📝 Select Source for Information Extraction**\n\n"
        "Choose where to extract file information from:\n"
        "• Caption: Uses file caption for extraction\n"
        "• Filename: Uses filename for extraction\n\n"
        f"Current Source: **{SOURCE_TYPES[source_type]}**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await callback_query.answer(f"Source changed to: {SOURCE_TYPES[source_type]}")

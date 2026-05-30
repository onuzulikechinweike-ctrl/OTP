import os
import re
import json
import asyncio
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeDefault
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

from ivasms_client import IVASSMSClient

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@your_channel")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
IVASMS_EMAIL = os.getenv("IVASMS_EMAIL")
IVASMS_PASSWORD = os.getenv("IVASMS_PASSWORD")

# Global IVASMS client
ivasms = IVASSMSClient(IVASMS_EMAIL, IVASMS_PASSWORD)

# Service mapping
SERVICES = {
    "facebook": "Facebook",
    "whatsapp": "WhatsApp",
    "tiktok": "TikTok",
    "instagram": "Instagram"
}

SERVICE_EMOJIS = {
    "facebook": "🔵",
    "whatsapp": "🟢",
    "tiktok": "🎵",
    "instagram": "🟣"
}

# In-memory user session storage
user_sessions = {}  # {user_id: {service, country, numbers, selected_number, range, timestamp}}


def is_owner(user_id):
    """Check if user is the bot owner."""
    return user_id == OWNER_ID


async def set_commands(app: Application):
    """Set bot commands with menu button."""
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("numbers", "📋 View my numbers"),
        BotCommand("otp", "🔑 Check OTP status"),
    ]

    # Add owner-only commands if owner ID is set
    if OWNER_ID:
        commands.append(BotCommand("broadcast", "📢 Send message to all users (Owner only)"))
        commands.append(BotCommand("stats", "📊 View bot statistics (Owner only)"))

    await app.bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def check_membership(user_id, context):
    """Check if user is a member of the channel. Owner always passes."""
    if is_owner(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.warning(f"Membership check error for {user_id}: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    user_id = user.id

    # Greet owner differently
    if is_owner(user_id):
        await update.message.reply_text(
            f"👑 **Welcome back Owner {user.first_name}!**\n\n"
            f"You have full access to all features.\n"
            f"Use /broadcast to send messages to all users.\n"
            f"Use /stats to view bot statistics.",
            parse_mode=ParseMode.MARKDOWN
        )

    # Check channel membership
    is_member = await check_membership(user_id, context)

    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 I've Joined", callback_data="verify_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚧 ACCESS DENIED 🚫🚧\n\nYou must join the channel below 👇",
            reply_markup=reply_markup
        )
        return

    # User is a member — show welcome
    keyboard = [
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['facebook']} Facebook", callback_data="svc_facebook")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['whatsapp']} WhatsApp", callback_data="svc_whatsapp")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['tiktok']} TikTok", callback_data="svc_tiktok")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['instagram']} Instagram", callback_data="svc_instagram")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Hello 👋 {user.first_name}\n\n"
        f"Welcome to 7𝕋ℍ 𝕆𝕋ℙ BOT.\n\n"
        f"Please choose a service from the available list below 👇",
        reply_markup=reply_markup
    )


async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'I've Joined' button click."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id

    is_member = await check_membership(user_id, context)

    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 I've Joined", callback_data="verify_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🚧 ACCESS DENIED 🚫🚧\n\nYou must join the channel below 👇",
            reply_markup=reply_markup
        )
        return

    # Show service selection
    keyboard = [
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['facebook']} Facebook", callback_data="svc_facebook")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['whatsapp']} WhatsApp", callback_data="svc_whatsapp")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['tiktok']} TikTok", callback_data="svc_tiktok")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['instagram']} Instagram", callback_data="svc_instagram")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"Hello 👋 {user.first_name}\n\n"
        f"Welcome to 7𝕋ℍ 𝕆𝕋ℙ BOT.\n\n"
        f"Please choose a service from the available list below 👇",
        reply_markup=reply_markup
    )


async def numbers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /numbers command — show service selection."""
    user = update.effective_user
    user_id = user.id

    is_member = await check_membership(user_id, context)
    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 I've Joined", callback_data="verify_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚧 ACCESS DENIED 🚫🚧\n\nYou must join the channel below 👇",
            reply_markup=reply_markup
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['facebook']} Facebook", callback_data="svc_facebook")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['whatsapp']} WhatsApp", callback_data="svc_whatsapp")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['tiktok']} TikTok", callback_data="svc_tiktok")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['instagram']} Instagram", callback_data="svc_instagram")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a service:", reply_markup=reply_markup)


async def otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /OTP command — show user current activations."""
    user_id = update.effective_user.id

    is_member = await check_membership(user_id, context)
    if not is_member:
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton("🔄 I've Joined", callback_data="verify_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🚧 ACCESS DENIED 🚫🚧\n\nYou must join the channel below 👇",
            reply_markup=reply_markup
        )
        return

    session = user_sessions.get(user_id, {})
    if not session or 'selected_number' not in session:
        await update.message.reply_text(
            "❌ No active number selected.\n"
            "Use /start or /numbers to select a service and country first."
        )
        return

    # Check OTP for the selected number
    await update.message.reply_text("🔍 Checking for OTP... Please wait...")

    otp_result = ivasms.get_otp_by_range_and_number(
        session['selected_number'],
        session['range']
    )

    if otp_result:
        msg_text = (
            f"📱 **OTP Received!**\n\n"
            f"🌍 **Country:** {session.get('country', 'N/A')}\n"
            f"🔧 **Service:** {session.get('service', 'N/A')}\n"
            f"📞 **Number:** `{session['selected_number']}`\n"
            f"🔑 **OTP Code:** `{otp_result['code']}`\n\n"
            f"📝 **Full Message:**\n`{otp_result['full_message']}`"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 New Number", callback_data=f"change_num_{session.get('service_key', '')}")],
            [InlineKeyboardButton("🌍 Change Country", callback_data=f"back_country_{session.get('service_key', '')}")],
            [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

        # Also drop OTP in the group if configured
        if GROUP_ID:
            try:
                group_msg = (
                    f"🔔 **New OTP Received**\n\n"
                    f"👤 User: {update.effective_user.first_name} (ID: {user_id})\n"
                    f"🌍 Country: {session.get('country', 'N/A')}\n"
                    f"🔧 Service: {session.get('service', 'N/A')}\n"
                    f"📞 Number: `{session['selected_number']}`\n"
                    f"🔑 OTP: `{otp_result['code']}`\n"
                    f"📝 Message: `{otp_result['full_message']}`"
                )
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=group_msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send to group: {e}")
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Check Again", callback_data=f"check_otp_{session.get('service_key', '')}")],
            [InlineKeyboardButton("🔄 New Number", callback_data=f"change_num_{session.get('service_key', '')}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back_country_{session.get('service_key', '')}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⏳ No OTP received yet.\n"
            "The number is still active and waiting for incoming messages.\n"
            "Use the buttons below to check again or get a new number.",
            reply_markup=reply_markup
        )


async def service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle service selection."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    service_key = query.data.replace("svc_", "")
    service_name = SERVICES.get(service_key, service_key.capitalize())

    # Store service in session
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['service'] = service_name
    user_sessions[user_id]['service_key'] = service_key

    # Fetch countries from IVASMS My Numbers
    await query.edit_message_text(
        f"🔄 Loading available countries for {SERVICE_EMOJIS.get(service_key, '')} {service_name}...\n"
        f"Please wait..."
    )

    countries = await asyncio.to_thread(ivasms.get_my_numbers)

    if not countries:
        keyboard = [[InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❌ No countries available.\n"
            "Please add numbers to your IVASMS account first.\n"
            "Go to Client System > My Numbers in IVASMS.",
            reply_markup=reply_markup
        )
        return

    # Build country selection keyboard
    keyboard = []
    row = []
    sorted_countries = sorted(countries.keys())
    for i, country in enumerate(sorted_countries):
        num_count = len(countries[country])
        btn_text = f"{country} ({num_count})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"cnt_{country}_{service_key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Service selected: {SERVICE_EMOJIS.get(service_key, '')} {service_name}\n\n"
        f"🌍 **Select Country:**\n"
        f"Choose from the available countries below 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle country selection and get a random number."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data.replace("cnt_", "")
    # Parse: country_servicekey
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ Error parsing selection.")
        return

    country_name = parts[0]
    service_key = parts[1]

    if user_id not in user_sessions:
        user_sessions[user_id] = {}

    user_sessions[user_id]['country'] = country_name
    user_sessions[user_id]['service_key'] = service_key
    user_sessions[user_id]['service'] = SERVICES.get(service_key, service_key.capitalize())

    # Fetch numbers for this country
    await query.edit_message_text(
        f"🔄 Getting a number for {country_name}...\nPlease wait..."
    )

    countries = await asyncio.to_thread(ivasms.get_my_numbers)

    if country_name not in countries or not countries[country_name]:
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Countries", callback_data=f"back_country_{service_key}")],
            [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"❌ No numbers available for {country_name}.\n"
            f"Please add numbers to this country in IVASMS.",
            reply_markup=reply_markup
        )
        return

    # Get a random number from the list
    import random
    numbers = countries[country_name]
    selected_number = random.choice(numbers)

    # Store in session
    user_sessions[user_id]['selected_number'] = selected_number
    user_sessions[user_id]['numbers'] = numbers
    user_sessions[user_id]['country_numbers'] = numbers

    # Get range for OTP lookup
    ranges = await asyncio.to_thread(ivasms.get_client_active_sms)
    found_range = None
    for cname, range_val in ranges.items():
        if cname.lower() in country_name.lower() or country_name.lower() in cname.lower():
            found_range = range_val
            break

    if not found_range:
        found_range = country_name

    user_sessions[user_id]['range'] = found_range
    user_sessions[user_id]['timestamp'] = time.time()

    # Build message with number display
    msg_text = (
        f"✅ **Country:** {country_name}\n"
        f"🔧 **Service:** {SERVICE_EMOJIS.get(service_key, '')} {user_sessions[user_id]['service']}\n\n"
        f"📞 **Your Number:**\n"
        f"`{selected_number}`\n\n"
        f"👆 Tap the number above to copy it\n\n"
        f"🔄 Use the number and wait for OTP..."
    )

    keyboard = [
        [InlineKeyboardButton("📋 Tap to Copy Number", callback_data=f"copy_{selected_number}")],
        [InlineKeyboardButton("🔄 Change Number", callback_data=f"change_num_{service_key}")],
        [InlineKeyboardButton("🌍 Change Country", callback_data=f"back_country_{service_key}")],
        [InlineKeyboardButton("🔑 Check OTP", callback_data=f"check_otp_{service_key}")],
        [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        msg_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def check_otp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle OTP check button."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    service_key = data.replace("check_otp_", "")

    session = user_sessions.get(user_id, {})

    if not session or 'selected_number' not in session:
        await query.edit_message_text(
            "❌ No active number. Please start over.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")
            ]])
        )
        return

    await query.edit_message_text(
        "🔍 Checking for OTP... Please wait...\n"
        "This may take a few seconds..."
    )

    otp_result = await asyncio.to_thread(
        ivasms.get_otp_by_range_and_number,
        session['selected_number'],
        session.get('range', '')
    )

    if otp_result:
        msg_text = (
            f"📱 **OTP Received!**\n\n"
            f"🌍 **Country:** {session.get('country', 'N/A')}\n"
            f"🔧 **Service:** {session.get('service', 'N/A')}\n"
            f"📞 **Number:** `{session['selected_number']}`\n"
            f"🔑 **OTP Code:** `{otp_result['code']}`\n\n"
            f"📝 **Full Message:**\n`{otp_result['full_message']}`"
        )

        keyboard = [
            [InlineKeyboardButton("📋 Copy OTP", callback_data=f"copy_{otp_result['code']}")],
            [InlineKeyboardButton("🔄 New Number", callback_data=f"change_num_{service_key}")],
            [InlineKeyboardButton("🌍 Change Country", callback_data=f"back_country_{service_key}")],
            [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

        # Drop in group
        if GROUP_ID:
            try:
                group_msg = (
                    f"🔔 **New OTP Received**\n\n"
                    f"👤 User: {query.from_user.first_name} (ID: {user_id})\n"
                    f"🌍 Country: {session.get('country', 'N/A')}\n"
                    f"🔧 Service: {session.get('service', 'N/A')}\n"
                    f"📞 Number: `{session['selected_number']}`\n"
                    f"🔑 OTP: `{otp_result['code']}`\n"
                    f"📝 Message: `{otp_result['full_message']}`"
                )
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=group_msg,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send to group: {e}")
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Check Again", callback_data=f"check_otp_{service_key}")],
            [InlineKeyboardButton("🔄 New Number", callback_data=f"change_num_{service_key}")],
            [InlineKeyboardButton("🌍 Change Country", callback_data=f"back_country_{service_key}")],
            [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⏳ **No OTP received yet.**\n\n"
            f"📞 **Number:** `{session.get('selected_number', 'N/A')}`\n\n"
            "The number is still active. Please wait for the SMS to arrive,\n"
            "then click 'Check Again' below.\n\n"
            "💡 Tip: You can also use a new number if this one isn't working.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def change_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle change number — get another random number."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    service_key = data.replace("change_num_", "")

    session = user_sessions.get(user_id, {})

    if 'numbers' not in session or not session['numbers']:
        # Re-fetch numbers
        countries = await asyncio.to_thread(ivasms.get_my_numbers)
        country_name = session.get('country', '')
        if country_name in countries and countries[country_name]:
            session['numbers'] = countries[country_name]
        else:
            await query.edit_message_text(
                "❌ No numbers available. Please select a country again.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data=f"back_country_{service_key}")
                ]])
            )
            return

    import random
    numbers = session['numbers']
    # Pick a different number if possible
    current = session.get('selected_number', '')
    available = [n for n in numbers if n != current]
    if not available:
        available = numbers

    new_number = random.choice(available)
    session['selected_number'] = new_number
    session['otp_notified'] = False

    msg_text = (
        f"✅ **New Number Selected!**\n\n"
        f"🌍 **Country:** {session.get('country', 'N/A')}\n"
        f"🔧 **Service:** {session.get('service', 'N/A')}\n\n"
        f"📞 **Your Number:**\n"
        f"`{new_number}`\n\n"
        f"👆 Tap the number above to copy it"
    )

    keyboard = [
        [InlineKeyboardButton("📋 Tap to Copy Number", callback_data=f"copy_{new_number}")],
        [InlineKeyboardButton("🔄 Change Number", callback_data=f"change_num_{service_key}")],
        [InlineKeyboardButton("🌍 Change Country", callback_data=f"back_country_{service_key}")],
        [InlineKeyboardButton("🔑 Check OTP", callback_data=f"check_otp_{service_key}")],
        [InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        msg_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def back_country_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to country selection."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    service_key = data.replace("back_country_", "")

    await query.edit_message_text(
        f"🔄 Loading countries... Please wait..."
    )

    countries = await asyncio.to_thread(ivasms.get_my_numbers)

    if not countries:
        keyboard = [[InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❌ No countries available.",
            reply_markup=reply_markup
        )
        return

    keyboard = []
    row = []
    for i, country in enumerate(sorted(countries.keys())):
        num_count = len(countries[country])
        btn_text = f"{country} ({num_count})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"cnt_{country}_{service_key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Services", callback_data="back_services")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🌍 **Select Country:**\n"
        f"Choose from the available countries below 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def back_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to main service selection."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id in user_sessions:
        # Keep only user info, clear session data
        user_sessions[user_id] = {}

    keyboard = [
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['facebook']} Facebook", callback_data="svc_facebook")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['whatsapp']} WhatsApp", callback_data="svc_whatsapp")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['tiktok']} TikTok", callback_data="svc_tiktok")],
        [InlineKeyboardButton(f"{SERVICE_EMOJIS['instagram']} Instagram", callback_data="svc_instagram")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "Please choose a service from the available list below 👇",
        reply_markup=reply_markup
    )


async def copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle copy button - send the value as a message so user can copy."""
    query = update.callback_query
    await query.answer()

    data = query.data
    value_to_copy = data.replace("copy_", "")

    # Send the copyable value as a new message
    await query.message.reply_text(
        f"📋 **Copied:** `{value_to_copy}`\n\n"
        f"Just select and copy the text above.",
        parse_mode=ParseMode.MARKDOWN
    )


# ==================== OWNER COMMANDS ====================

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Broadcast a message to all active users."""
    user_id = update.effective_user.id

    if not is_owner(user_id):
        await update.message.reply_text("❌ Only the bot owner can use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "📢 **Usage:** `/broadcast <message>`\n\n"
            "Example: `/broadcast Hello everyone! The bot is under maintenance.`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    message = " ".join(context.args)
    sent_count = 0
    failed_count = 0

    status_msg = await update.message.reply_text(
        "📢 Broadcasting message to all active users..."
    )

    for uid in list(user_sessions.keys()):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 **Broadcast from Owner:**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning(f"Broadcast failed for user {uid}: {e}")

    await status_msg.edit_text(
        f"📢 **Broadcast Complete!**\n\n"
        f"✅ Sent: {sent_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"👥 Total users in session: {len(user_sessions)}"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: View bot statistics."""
    user_id = update.effective_user.id

    if not is_owner(user_id):
        await update.message.reply_text("❌ Only the bot owner can use this command.")
        return

    total_users = len(user_sessions)
    active_sessions = sum(
        1 for s in user_sessions.values()
        if s.get('selected_number') is not None
    )

    # Count unique countries and services in use
    countries_in_use = set()
    services_in_use = {}
    for s in user_sessions.values():
        if s.get('country'):
            countries_in_use.add(s['country'])
        if s.get('service'):
            svc = s['service']
            services_in_use[svc] = services_in_use.get(svc, 0) + 1

    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"📱 **Active Sessions:** {active_sessions}\n"
        f"🌍 **Countries in Use:** {len(countries_in_use)}\n"
        f"🔧 **Services Breakdown:**\n"
    )
    for svc, count in services_in_use.items():
        stats_text += f"   • {svc}: {count}\n"

    stats_text += f"\n⏰ **Bot Uptime:** Running since last start"

    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)


async def auto_otp_monitor():
    """
    Background task that monitors active sessions for OTPs.
    Runs in a separate thread.
    """
    logger.info("Starting auto OTP monitor...")
    while True:
        try:
            for user_id, session in list(user_sessions.items()):
                if session.get('selected_number') and session.get('range') and not session.get('otp_notified'):
                    otp_result = ivasms.get_otp_by_range_and_number(
                        session['selected_number'],
                        session.get('range', '')
                    )
                    if otp_result:
                        logger.info(f"Auto-detected OTP for user {user_id}: {otp_result['code']}")
                        session['otp_notified'] = True
            time.sleep(10)
        except Exception as e:
            logger.error(f"Auto OTP monitor error: {e}")
            time.sleep(30)


def main():
    """Main entry point."""
    logger.info("Starting 7TH OTP Bot...")

    if not OWNER_ID:
        logger.warning("OWNER_ID is not set! Owner features will be unavailable.")

    # Login to IVASMS
    if not ivasms.login():
        logger.error("Failed to login to IVASMS. Check your credentials.")
        return

    # Pre-fetch countries
    logger.info("Pre-fetching countries and numbers...")
    countries = ivasms.get_my_numbers()
    logger.info(f"Loaded {len(countries)} countries from IVASMS")

    # Create application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("numbers", numbers_command))
    app.add_handler(CommandHandler("otp", otp_command))

    # Owner commands
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Callback query handlers
    app.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    app.add_handler(CallbackQueryHandler(service_callback, pattern="^svc_"))
    app.add_handler(CallbackQueryHandler(country_callback, pattern="^cnt_"))
    app.add_handler(CallbackQueryHandler(check_otp_callback, pattern="^check_otp_"))
    app.add_handler(CallbackQueryHandler(change_number_callback, pattern="^change_num_"))
    app.add_handler(CallbackQueryHandler(back_country_callback, pattern="^back_country_"))
    app.add_handler(CallbackQueryHandler(back_services_callback, pattern="^back_services$"))
    app.add_handler(CallbackQueryHandler(copy_callback, pattern="^copy_"))

    # Set commands
    app.post_init = set_commands

    # Start background OTP monitor thread
    monitor_thread = threading.Thread(target=auto_otp_monitor, daemon=True)
    monitor_thread.start()

    # Start polling
    logger.info("Bot is running... Press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
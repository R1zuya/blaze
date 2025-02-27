from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
    MessageHandler,
    filters,
)
import datetime
import logging
import os

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Bot Token ---
TOKEN = "7972422177:AAGTkCgvKuYLu16qdzB1LrnidxvKwB1n93E"  # **REPLACE WITH YOUR ACTUAL BOT TOKEN**
REVIEW_CHANNEL_ID = -1001497637176
ACCEPTED_CHANNEL_ID = -1002473966689

if not TOKEN:
    print("Bot token not set in blaze.py. Please enter your token in blaze.py.")
    exit()

# --- User Data ---
USER_DATA = {}

# --- Auction Logic ---
ACTIVE_AUCTIONS = {}
AUCTION_ID_COUNTER = 1

# --- Conversation States for /add command ---
(
    ADD_POKEMON_TYPE,
    GET_POKEMON_NAME,
    GET_POKEMON_INFO_PAGE,
    GET_POKEMON_IVS_PAGE,
    GET_BOOSTED_INFO,
    SUBMISSION_CONFIRMATION, # Added a new state for explicit confirmation (not used yet but good practice)
) = range(6) # Corrected range to 6 states

# --- Log Conversation State Values for Debugging ---
logger.info(f"State ADD_POKEMON_TYPE: {ADD_POKEMON_TYPE}")
logger.info(f"State GET_POKEMON_NAME: {GET_POKEMON_NAME}")
logger.info(f"State GET_POKEMON_INFO_PAGE: {GET_POKEMON_INFO_PAGE}")
logger.info(f"State GET_POKEMON_IVS_PAGE: {GET_POKEMON_IVS_PAGE}")
logger.info(f"State GET_BOOSTED_INFO: {GET_BOOSTED_INFO}")
logger.info(f"State SUBMISSION_CONFIRMATION: {SUBMISSION_CONFIRMATION}") # Log new state


# --- Auction Logic Functions (retained - with async fixes) ---
async def create_new_auction(item_description, starting_price, duration_minutes, creator_id, creator_name):
    global AUCTION_ID_COUNTER
    auction_id = AUCTION_ID_COUNTER
    AUCTION_ID_COUNTER += 1
    end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration_minutes)
    ACTIVE_AUCTIONS[auction_id] = {
        "auction_id": auction_id,
        "item_description": item_description,
        "starting_price": starting_price,
        "current_price": starting_price,
        "end_time": end_time,
        "status": "active",
        "bids": {},
        "creator_id": creator_id,
        "creator_name": creator_name
    }
    logger.info(f"Auction {auction_id} created for {item_description} by {creator_name}")
    return auction_id

async def place_bid(auction_id, bidder_id, bid_amount, bidder_name):
    auction = ACTIVE_AUCTIONS.get(auction_id)
    if not auction:
        return "Auction not found."
    if auction["status"] != "active":
        return "This auction is not active."
    if bid_amount <= auction["current_price"]:
        return f"Your bid must be higher than the current price: {auction['current_price']}."

    auction["bids"][bidder_id] = bid_amount
    auction["current_price"] = bid_amount
    logger.info(f"Bid of {bid_amount} placed by {bidder_name} (ID {bidder_id}) on auction {auction_id}")
    return f"Bid placed successfully! Current highest bid: {bid_amount}."

async def end_auction(auction_id, context: CallbackContext):
    auction = ACTIVE_AUCTIONS.get(auction_id)
    if not auction:
        return "Auction not found."
    if auction["status"] != "active":
        return "Auction is not active."

    auction["status"] = "ended"
    logger.info(f"Auction {auction_id} ended.")

    if auction["bids"]:
        highest_bidder_id = max(auction["bids"], key=auction["bids"].get)
        highest_bid = auction["bids"][highest_bidder_id]
        winner_name = ""
        message_text = f"Auction {auction_id} for {auction['item_description']} has ended!\nWinner: Trainer ID {highest_bidder_id} with bid: {highest_bid}."
    else:
        message_text = f"Auction {auction_id} for {auction['item_description']} has ended with no bids."

    chat_id = USER_DATA.get('chat_id')
    if chat_id:
        await context.bot.send_message(chat_id=chat_id, text=message_text)
    else:
        logger.warning("Chat ID not found, cannot send end auction message.")

    del ACTIVE_AUCTIONS[auction_id]

def get_auction_details_text(auction_id):
    auction = ACTIVE_AUCTIONS.get(auction_id)
    if not auction:
        return "Auction not found."

    time_remaining = auction["end_time"] - datetime.datetime.now()
    minutes_remaining = int(time_remaining.total_seconds() / 60)
    seconds_remaining = int(time_remaining.total_seconds() % 60)

    bids_text = "No bids yet for this Pokemon."
    if auction["bids"]:
        highest_bidder_id = max(auction["bids"], key=auction["bids"].get)
        highest_bid = auction["bids"][highest_bidder_id]
        bids_text = f"Current highest bid: {highest_bid} by Trainer ID {highest_bidder_id}"

    auction_text = f"**Pokemon Auction ID:** {auction['auction_id']}\n"
    auction_text += f"**Pokemon:** {auction['item_description']}\n"
    auction_text += f"**Starting Price:** {auction['starting_price']}\n"
    auction_text += f"**Current Price:** {auction['current_price']}\n"
    auction_text += f"**Time Remaining:** {minutes_remaining} minutes {seconds_remaining} seconds\n"
    auction_text += f"**Status:** {auction['status'].capitalize()}\n"
    auction_text += f"**Bids:** {bids_text}\n"
    auction_text += f"**Auction Creator:** Trainer {auction['creator_name']}\n"

    return auction_text

def list_active_auctions():
    if not ACTIVE_AUCTIONS:
        return "No active Pokemon auctions at the moment."

    auction_list_text = "*Active Pokemon Auctions:*\n\n"
    for auction_id, auction in ACTIVE_AUCTIONS.items():
        auction_list_text += f"Auction ID: {auction_id} - Pokemon: {auction['item_description']} - Current Price: {auction['current_price']}\n"

    return auction_list_text

async def setup_auction_end_job(context: CallbackContext):
    now = datetime.datetime.now()
    ended_auction_ids = []
    for auction_id, auction in ACTIVE_AUCTIONS.items():
        if auction["status"] == "active" and auction["end_time"] <= now:
            await end_auction(auction_id, context)  # Add 'await' here
            ended_auction_ids.append(auction_id)

    if ended_auction_ids:
        logger.info(f"Ended auctions: {ended_auction_ids}")

async def show_auction_details_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    auction_id = int(query.data.split('_')[-1])
    auction_details = get_auction_details_text(auction_id)
    await query.message.reply_text(auction_details, parse_mode="Markdown")

async def list_auctions_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    auction_list_text = list_active_auctions()

    keyboard = []
    if ACTIVE_AUCTIONS:
        for auction_id in ACTIVE_AUCTIONS:
            keyboard.append([InlineKeyboardButton(f"View Auction {auction_id} Details", callback_data=f'auction_details_{auction_id}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(auction_list_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await query.message.reply_text(auction_list_text, parse_mode="Markdown")

# --- Command Handlers for /add Conversation ---
async def add_command_handler(update: Update, context: CallbackContext) -> int:
    logger.info("User initiated /add command") # Log command start
    message_text = "╭─━─━─━─━─≪✠≫─━─━─━─━─╮\n\n" \
                   "Which type of Pokemon you want to add\n\n" \
                   "༺═──────────────────═༻"

    keyboard = [
        [
            InlineKeyboardButton("6L", callback_data='add_pokemon_type_6L'),
            InlineKeyboardButton("0L", callback_data='add_pokemon_type_0L'),
            InlineKeyboardButton("Shiny", callback_data='add_pokemon_type_shiny')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message_text, reply_markup=reply_markup)
    return ADD_POKEMON_TYPE # Set state to ADD_POKEMON_TYPE

async def add_pokemon_type_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    pokemon_type = query.data.split('_')[-1] # Extract pokemon_type (6L, 0L, Shiny)
    context.user_data['pokemon_type'] = pokemon_type # Store pokemon type
    logger.info(f"Pokemon type selected: {pokemon_type}") # Log pokemon type
    await query.message.reply_text("Send your pokemon name")
    return GET_POKEMON_NAME # Next state: get pokemon name

async def get_pokemon_name(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text
    context.user_data['pokemon_name'] = user_input # Store Pokemon name
    logger.info(f"Pokemon name received: {user_input}") # Log pokemon name
    await update.message.reply_text(f"Send Pokemon Info Page! From @HeXamonbot")
    return GET_POKEMON_INFO_PAGE # Next state: get info page

async def get_pokemon_info_page(update: Update, context: CallbackContext) -> int:
    logger.info("Entering get_pokemon_info_page handler - storing info page details") # Log entry

    message_dict = update.message.to_dict()

    if 'forward_origin' in message_dict:
        forward_origin_info = message_dict['forward_origin']

        if forward_origin_info and forward_origin_info.get('sender_user'):
            sender_user_info = forward_origin_info['sender_user']

            if sender_user_info.get('username') == 'HeXamonbot':
                message_text = update.message.caption or update.message.text or "" # Get caption or text
                photo = update.message.photo # Get photo object if available

                context.user_data['pokemon_info_page_text'] = message_text # Store Info Page text
                context.user_data['pokemon_info_page_photo'] = photo # Store Info Page photo (can be None)

                logger.info("Info Page Text stored in user_data") # Log text storage
                if photo:
                    logger.info("Info Page Photo stored in user_data") # Log photo storage

                await update.message.reply_text("Forward Pokemon Ivs Page! From @HeXamonbot (Info Page Confirmed and Saved)")
                return GET_POKEMON_IVS_PAGE
            else:
                await update.message.reply_text("Please forward the Pokemon Info Page from @HeXamonbot. Make sure to forward from the correct bot.")
                return GET_POKEMON_INFO_PAGE
        else:
            await update.message.reply_text("Please forward the Pokemon Info Page from @HeXamonbot. Make sure to forward from the correct bot.")
            return GET_POKEMON_INFO_PAGE
    else:
        await update.message.reply_text("Please forward the Pokemon Info Page. To forward a message, press and hold on the message, then select 'Forward' and choose this bot.")
        return GET_POKEMON_INFO_PAGE

async def get_pokemon_ivs_page(update: Update, context: CallbackContext) -> int:
    logger.info("Entering get_pokemon_ivs_page handler (DEBUG - ATTEMPT 2 - DICT and LOG TEXT)") # Debug log
    logger.info(f"Full update.message object: {update.message}") # Log full message

    message_dict = update.message.to_dict() # Convert message to dictionary

    if 'forward_origin' in message_dict: # Check for 'forward_origin' key in dictionary
        forward_origin_info = message_dict['forward_origin'] # Get forward_origin info

        if forward_origin_info and forward_origin_info.get('sender_user'): # Check for sender_user
            sender_user_info = forward_origin_info['sender_user'] # Get sender_user info

            if sender_user_info.get('username') == 'HeXamonbot': # Check username from dictionary
                message_text = update.message.caption or update.message.text or "" # Get caption or text
                logger.info(f"message_text for IVs Page: {message_text}") # LOG MESSAGE TEXT HERE!

                is_ivs_page = False

                # Keyword Checks for IVs Page (New Format) - Re-checking keywords here as well just in case
                if "HeXamonbot" in message_text and "Points" in message_text and "IV |" in message_text and "EV" in message_text and "HP" in message_text and "Attack" in message_text and "Defense" in message_text and "Sp. Attack" in message_text and "Sp. Defense" in message_text and "Speed" in message_text and "Total" in message_text:
                    logger.info("Keywords for IVs Page found (DEBUG - Attempt 2)") # Debug log
                    is_ivs_page = True
                elif forward_origin_info and sender_user_info.get('username') == 'HeXamonbot': # Secondary check - using dict access indirectly now
                    logger.info("Message is forwarded from HeXamonbot (using forward_origin from dict - DEBUG Attempt 2)") # Debug log
                    is_ivs_page = True
                else:
                    logger.info("Neither keywords nor valid forward_from found for IVs Page (DEBUG - Attempt 2)") # Debug log
                    is_ivs_page = False

                if is_ivs_page:
                    context.user_data['pokemon_ivs_page_text'] = message_text # Store IVs page text
                    context.user_data['pokemon_ivs_page'] = True
                    logger.info("IVs Page Confirmed. Asking for boosted info. (DEBUG - Attempt 2)") # Debug log
                    keyboard = [
                        [InlineKeyboardButton("Yes", callback_data='boosted_yes'), InlineKeyboardButton("No", callback_data='boosted_no')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text("Boosted? Yes or No (if Yes also mention which ivs you boosted in the pokemon )", reply_markup=reply_markup)
                    return GET_BOOSTED_INFO # Next state: get boosted info
                else:
                    await update.message.reply_text("Please forward the Pokemon IVs Page correctly from @HeXamonbot. Ensure it contains 'Points', 'IV |', 'EV', 'HP', 'Attack', 'Defense', 'Sp. Attack', 'Sp. Defense', 'Speed', 'Total' and is from @HeXamonbot.", parse_mode="HTML")
                    logger.info("IVs Page NOT Confirmed - Incorrect format. (DEBUG - Attempt 2)") # Debug log
                    return GET_POKEMON_IVS_PAGE # Stay in GET_POKEMON_IVS_PAGE state
            else:
                await update.message.reply_text("Please forward the Pokemon Ivs Page from @HeXamonbot. Make sure to forward from the correct bot.")
                logger.info("IVs Page NOT Confirmed - Not forwarded from HeXamonbot. (DEBUG - Attempt 2)") # Debug log
                return GET_POKEMON_IVS_PAGE # Stay in GET_POKEMON_IVS_PAGE state
        else:
            await update.message.reply_text("Please forward the Pokemon Ivs Page from @HeXamonbot. Make sure to forward from the correct bot.")
            logger.info(" 'forward_origin' or 'sender_user' NOT found in dict. (DEBUG - Attempt 2)") # Debug log
            return GET_POKEMON_IVS_PAGE # Stay in GET_POKEMON_IVS_PAGE state
    else:
        await update.message.reply_text("Please forward the Pokemon Ivs Page. To forward a message, press and hold on the message, then select 'Forward' and choose this bot.")
        logger.info("IVs Page NOT Confirmed - Not forwarded message. (DEBUG - Attempt 2)") # Debug log
        return GET_POKEMON_IVS_PAGE # Stay in GET_POKEMON_IVS_PAGE state

async def get_boosted_info_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    boosted_choice = query.data.split('_')[-1] # Get boosted choice (yes/no)
    context.user_data['boosted'] = boosted_choice
    logger.info(f"Boosted choice: {boosted_choice}") # Log boosted choice

    if boosted_choice == 'yes':
        await query.message.reply_text("Mention which IVs you boosted in the Pokemon (e.g., Speed, Attack). If no boost mention No Boost")
        return GET_BOOSTED_INFO # Stay in this state to get boosted IV details
    else:
        context.user_data['boosted_ivs_details'] = "No Boost"
        return await end_submission_process(update, context, update.effective_user) # Go to submission

async def get_boosted_info_text(update: Update, context: CallbackContext) -> int:
    boosted_ivs_details = update.message.text
    context.user_data['boosted_ivs_details'] = boosted_ivs_details # Store boosted IV details
    logger.info(f"Boosted IV details received: {boosted_ivs_details}") # Log boosted IV details
    return await end_submission_process(update, context, update.effective_user) # Go to submission

async def end_submission_process(update: Update, context: CallbackContext, user):
    logger.info("Entering end_submission_process handler") # Log entry
    pokemon_type = context.user_data.get('pokemon_type')
    pokemon_name = context.user_data.get('pokemon_name')
    boosted = context.user_data.get('boosted')
    boosted_ivs_details = context.user_data.get('boosted_ivs_details')
    pokemon_info_page_photo = context.user_data.get('pokemon_info_page_photo')

    review_message_text = create_review_message(context.user_data, user)

    keyboard = [
        [InlineKeyboardButton("Accept", callback_data='accept_auction'), InlineKeyboardButton("Reject", callback_data='reject_auction')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if REVIEW_CHANNEL_ID:
        try:
            if pokemon_info_page_photo:
                await context.bot.send_photo(chat_id=REVIEW_CHANNEL_ID, photo=pokemon_info_page_photo[-1].file_id, caption=review_message_text, reply_markup=reply_markup, parse_mode="HTML")
                logger.info("Review message with photo sent to review channel.") # Log photo sent
            else:
                await context.bot.send_message(chat_id=REVIEW_CHANNEL_ID, text=review_message_text, reply_markup=reply_markup, parse_mode="HTML")
                logger.info("Review message (text only) sent to review channel.") # Log text sent

        except Exception as e:
            logger.error(f"Error sending review message to channel: {e}")
            await update.callback_query.message.reply_text("Error sending to review channel. Check bot logs.")
            return ConversationHandler.END
    else:
        await update.callback_query.message.reply_text("Review Channel ID not set. Cannot submit for review.")
        return ConversationHandler.END

    submission_message = "! Pokemon Has been sent for submission ✅\n\n" \
                         "• Join: @shadow_auction\n" \
                         "• Trade Group: @ShadowHexaGroup\n" \
                         "Must join else your items will be removed!\n\n" \
                         "**Pokemon Type:** " + pokemon_type + "\n" \
                         "**Pokemon Name:** " + pokemon_name + "\n" \
                         "**Boosted:** " + boosted + "\n" \
                         "**Boosted IVs Details:** " + boosted_ivs_details

    await update.callback_query.message.reply_text(submission_message, parse_mode="Markdown")
    logger.info("Submission confirmation sent to user.") # Log confirmation to user

    context.user_data.clear() # Clear user data
    logger.info("User data cleared. Ending /add conversation.") # Log data clear and conversation end
    return ConversationHandler.END

def create_review_message(user_data, user):
    pokemon_type = user_data.get('pokemon_type')
    pokemon_name = user_data.get('pokemon_name')
    boosted = user_data.get('boosted')
    boosted_ivs_details = user_data.get('boosted_ivs_details')
    info_page_text = user_data.get('pokemon_info_page_text', 'No Info Page Text')
    ivs_page_text = user_data.get('pokemon_ivs_page_text', 'No IVs Page Text')

    review_message_text = "<b>New Pokemon Auction Submission</b>\n\n" \
                          f"<b>Pokemon Type:</b> {pokemon_type}\n" \
                          f"<b>Pokemon Name:</b> {pokemon_name}\n" \
                          f"<b>Boosted:</b> {boosted}\n" \
                          f"<b>Boosted IVs Details:</b> {boosted_ivs_details}\n\n" \
                          f"<b>Info Page Text:</b>\n<code>{info_page_text}</code>\n\n" \
                          f"<b>IVs Page Text:</b>\n<code>{ivs_page_text}</code>\n\n" \
                          f"Submitted by: {user.first_name} (ID: <code>{user.id}</code>)"
    return review_message_text


async def add_pokemon_type_callback(update: Update, context: CallbackContext) -> int: # No changes needed here - already correct
    query = update.callback_query
    await query.answer()
    pokemon_type = query.data.split('_')[-1]
    context.user_data['pokemon_type'] = pokemon_type
    logger.info(f"Pokemon type selected via button: {pokemon_type}") # Log button selection
    await query.message.reply_text("Send your pokemon name")
    return GET_POKEMON_NAME

async def cancel_submission(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    await update.message.reply_text(
        f"Submission cancelled by {user.first_name}. Use /add again to start over."
    )
    logger.info("Submission cancelled by user.") # Log cancellation
    context.user_data.clear()
    return ConversationHandler.END

# --- Review and Auction Management Handlers (No changes needed here) ---
async def accept_auction_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer("Pokemon Auction Accepted!")
    accepted_channel_id = ACCEPTED_CHANNEL_ID
    if accepted_channel_id:
        try:
            await context.bot.forward_message(chat_id=accepted_channel_id, from_chat_id=query.message.chat_id, message_id=query.message.message_id)
        except Exception as e:
            logger.error(f"Error forwarding to accepted channel: {e}")
            await query.message.reply_text("Error forwarding to accepted channel. Check bot logs.")
    else:
        await query.message.reply_text("Accepted Channel ID not set. Cannot forward.")

    submitted_by_line = query.message.text.splitlines()[-1]
    user_id_str = submitted_by_line.split('(ID: <code>')[1].split('</code>')[0]
    try:
        user_id = int(user_id_str)
        await context.bot.send_message(chat_id=user_id, text="🎉 Congratulations! Your Pokemon auction submission has been accepted and forwarded to the auction channel.")
    except (IndexError, ValueError):
        logger.warning(f"Could not extract user ID from review message to send acceptance notification.")

async def reject_auction_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer("Pokemon Auction Rejected.")
    submitted_by_line = query.message.text.splitlines()[-1]
    user_id_str = submitted_by_line.split('(ID: <code>')[1].split('</code>')[0]
    try:
        user_id = int(user_id_str)
        await context.bot.send_message(chat_id=user_id, text="😔 Sorry, your Pokemon auction submission has been rejected.")
    except (IndexError, ValueError):
        logger.warning(f"Could not extract user ID from review message to send rejection notification.")
    await query.message.delete()

# ---  Initial Handlers (No changes needed here) ---
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    welcome_message = f"Welcome to Shadow Auction Bot, {user.first_name}!\n\n" \
                      "This bot is used to manage auctions in Shadow Auction (Based on Slow Auctions).\n\n" \
                      "⚠️ <b>Must join Both Channel & Groups</b>\n" \
                      "Auction Group:\n" \
                      "╰➤ <a href='https://t.me/Shadow_Auction'>@Shadow_Auction</a>\n\n" \
                      "Auction Trade Group:\n" \
                      "╰➤ <a href='https://t.me/ShadowHexaGroup'>@ShadowHexaGroup</a>\n\n" \
                      "Use /add to add your Pokemon for auction.\n\n" \
                      f"Share this bot: <a href='https://telegram.me/share/url?url=https://files.catbox.moe/dv2lv8.jpg'>Share Image</a>"

    keyboard = [
        [
            InlineKeyboardButton("Auction Channel", url="https://t.me/Shadow_Auction"),
            InlineKeyboardButton("Auction Group", url="https://t.me/ShadowHexaGroup"),
            InlineKeyboardButton("Add Pokemon", callback_data='add_pokemon')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(chat_id=update.message.chat_id,
                                   photo="https://files.catbox.moe/dv2lv8.jpg",
                                   caption=welcome_message,
                                   parse_mode="HTML",
                                   reply_markup=reply_markup)
    USER_DATA['chat_id'] = update.message.chat_id

async def add_pokemon_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Please use the /add command to start adding a Pokemon for auction.")

# --- Command handlers outside conversation ---
async def bid_command_handler(update: Update, context: CallbackContext):
    try:
        args = update.message.text.split(' ')[1:]
        if len(args) != 2:
            await update.message.reply_text("Invalid format. Use: /bid AuctionID BidAmount to bid on Pokemon auctions.")
            return

        auction_id = int(args[0])
        bid_amount = int(args[1])
        user_id = update.message.from_user.id
        user_name = update.message.from_user.username or update.message.from_user.first_name

        result_message = await place_bid(auction_id, user_id, bid_amount, user_name) # Added await
        await update.message.reply_text(result_message)
        auction_details = get_auction_details_text(auction_id)
        await update.message.reply_text(auction_details, parse_mode="Markdown")

    except ValueError:
        await update.message.reply_text("Invalid auction ID or bid amount. Please use numbers.")
    except IndexError:
        await update.message.reply_text("Please provide auction ID and bid amount. Use: /bid AuctionID BidAmount for Pokemon auctions.")

async def auction_details_command_handler(update: Update, context: CallbackContext):
    try:
        auction_id = int(context.args[0])
        auction_details = get_auction_details_text(auction_id)
        await update.message.reply_text(auction_details, parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid auction ID. Please use a number.")
    except IndexError:
        await update.message.reply_text("Please provide auction ID. Use: /auction_details AuctionID to see Pokemon auction details.")

async def list_auctions_command_handler(update: Update, context: CallbackContext):
    auction_list_text = list_active_auctions()

    keyboard = []
    if ACTIVE_AUCTIONS:
        for auction_id in ACTIVE_AUCTIONS:
            keyboard.append([InlineKeyboardButton(f"View Auction {auction_id} Details", callback_data=f'auction_details_{auction_id}')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(auction_list_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(auction_list_text, parse_mode="Markdown")

# --- Post Initialization ---
async def post_initialization(context: CallbackContext):
    logger.info("Pokemon Auction Bot initialized and ready!")
    context.job_queue.run_repeating(setup_auction_end_job, interval=datetime.timedelta(minutes=1), first=0)

def main():
    app = Application.builder().token(TOKEN).post_init(post_initialization).build()

    # --- Conversation Handler for /add command ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_command_handler)],
        states={
            ADD_POKEMON_TYPE: [
                CallbackQueryHandler(add_pokemon_type_callback, pattern='^add_pokemon_type_'),
            ],
            GET_POKEMON_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pokemon_name)],
            GET_POKEMON_INFO_PAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, get_pokemon_info_page)], # Changed to filters.ALL
            GET_POKEMON_IVS_PAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, get_pokemon_ivs_page)],
            GET_BOOSTED_INFO: [
                CallbackQueryHandler(get_boosted_info_callback, pattern='^boosted_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_boosted_info_text)
            ],
            SUBMISSION_CONFIRMATION: [], # State not fully used yet, but could be added before end_submission
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, cancel_submission)]
        },
        fallbacks=[CommandHandler('cancel', cancel_submission)],
        conversation_timeout=datetime.timedelta(minutes=5)
    )
    app.add_handler(conv_handler)

    # --- Command handlers outside conversation ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bid", bid_command_handler))
    app.add_handler(CommandHandler("auction_details", auction_details_command_handler))
    app.add_handler(CommandHandler("list_auctions", list_auctions_command_handler))

    # --- Callback query handlers outside conversation ---
    app.add_handler(CallbackQueryHandler(add_pokemon_callback, pattern='^add_pokemon$'))
    app.add_handler(CallbackQueryHandler(accept_auction_callback, pattern='^accept_auction$'))
    app.add_handler(CallbackQueryHandler(reject_auction_callback, pattern='^reject_auction$'))

    # --- Start the Bot ---
    app.run_polling()

if __name__ == '__main__':
    main()

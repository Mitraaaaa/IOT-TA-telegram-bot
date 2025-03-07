import json
import os
import asyncio
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Patch the event loop (useful in interactive environments)
nest_asyncio.apply()

TOKEN = "8014320970:AAHmjPlIjITbp8VeNmyLpse-KPl0VsnMgAs"
IDEAS_FILE = "ideas.json"
ADMIN_PASSWORD = "IOT_TAs_403"  # admin password

# Load ideas from file or initialize an empty list.
if os.path.exists(IDEAS_FILE):
    try:
        with open(IDEAS_FILE, "r") as f:
            ideas = json.load(f)
    except json.decoder.JSONDecodeError:
        ideas = []
else:
    ideas = []

def save_ideas():
    with open(IDEAS_FILE, "w") as f:
        json.dump(ideas, f)

# Helper function to format member info as "TelegramName(@username)"
def format_member(member: dict) -> str:
    display = member.get("display", "")
    username = member.get("username", "")
    if username:
        return f"{display}(@{username})"
    else:
        return f"{display}"

# Conversation state for adding an idea.
ADDING_IDEA = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the Idea Bot!\n"
        "Commands:\n"
        "/add_idea - Submit an idea (prefix with 'anonymous:' for anonymous ideas)\n"
        "/all_ideas - View all ideas\n"
        "/owned_teams - View teams you created\n"
        "/joined_teams - View teams you have joined\n"
        "/admin_panel <password> - Admin panel to view and delete ideas"
    )

### /add_idea: submit a new idea (owner auto‑added to the team)
async def add_idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send me your idea:")
    return ADDING_IDEA

async def add_idea_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    if raw_text.lower().startswith("anonymous:"):
        idea_text = raw_text[len("anonymous:"):].strip()
        creator = "Anonymous"
        modifiable = False
    else:
        idea_text = raw_text
        # Use Telegram account's first name as display.
        creator = update.message.from_user.first_name
        modifiable = True

    user_id = update.message.from_user.id
    username = update.message.from_user.username or ""
    display = update.message.from_user.first_name  # default display name
    idea_entry = {
        "user": creator,
        "idea": idea_text,
        "chat_id": update.effective_chat.id,  # Owner's chat (assumed private)
        "team": [{"user_id": user_id, "display": display, "username": username}],
        "modifiable": modifiable
    }
    ideas.append(idea_entry)
    save_ideas()
    await update.message.reply_text("Your idea has been added!")
    return ConversationHandler.END

### /all_ideas: list all ideas with a "Request Participation" button when applicable.
async def all_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ideas:
        await update.message.reply_text("No ideas have been added yet.")
        return

    message_text = "All Ideas:\n"
    keyboard = []
    requester = update.message.from_user
    requester_id = requester.id
    requester_display = requester.first_name
    requester_username = requester.username or ""
    for idx, idea_entry in enumerate(ideas):
        if idea_entry.get("team"):
            owner_formatted = format_member(idea_entry["team"][0])
        else:
            owner_formatted = idea_entry["user"]
        message_text += f"{idx+1}. {idea_entry['idea']} (by {owner_formatted})\n"
        if requester_id != idea_entry["chat_id"] and not any(member["user_id"] == requester_id for member in idea_entry.get("team", [])):
            keyboard.append([InlineKeyboardButton(
                f"Request Participation #{idx+1}",
                callback_data=f"request:{idx}:{requester_id}:{requester_display}:{requester_username}"
            )])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(message_text, reply_markup=reply_markup)

### /owned_teams: show teams (ideas) that you created.
async def owned_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    found = False
    for idx, idea_entry in enumerate(ideas):
        if idea_entry["chat_id"] == chat_id:
            found = True
            text = f"Idea #{idx+1}: {idea_entry['idea']}\nTeam Members:\n"
            team = idea_entry.get("team", [])
            if len(team) <= 1:
                text += "No additional team members yet.\n"
            else:
                for member in team:
                    text += f"- {format_member(member)}\n"
            keyboard = []
            if idea_entry.get("modifiable") and len(team) > 1:
                for member in team:
                    if member["user_id"] != team[0]["user_id"]:
                        keyboard.append([InlineKeyboardButton(
                            f"Remove {member['display']}",
                            callback_data=f"remove:{idx}:{member['user_id']}"
                        )])
            # Add an inline button for owner deletion of the idea.
            keyboard.append([InlineKeyboardButton(
                "Delete Idea",
                callback_data=f"deleteidea:{idx}"
            )])
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    if not found:
        await update.message.reply_text("You haven't created any teams yet.")

### /joined_teams: show teams where you are a participant (not the owner).
async def joined_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    found = False
    for idx, idea_entry in enumerate(ideas):
        if any(member["user_id"] == user_id for member in idea_entry.get("team", [])) and user_id != idea_entry["chat_id"]:
            found = True
            owner = format_member(idea_entry["team"][0]) if idea_entry.get("team") else idea_entry["user"]
            text = f"Idea #{idx+1}: {idea_entry['idea']} (Owner: {owner})\nTeam Members:\n"
            team = idea_entry.get("team", [])
            if not team:
                text += "No team members.\n"
            else:
                for m in team:
                    text += f"- {format_member(m)}\n"
            await update.message.reply_text(text)
    if not found:
        await update.message.reply_text("You are not a member of any team (as a participant).")

### /admin_panel <password>: Admin panel to view all ideas and delete ideas.
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or args[0] != ADMIN_PASSWORD:
        await update.message.reply_text("Incorrect or missing password.")
        return
    admin_text = "Admin Panel: All Ideas and Teams:\n\n"
    keyboard = []
    for idx, idea_entry in enumerate(ideas):
        if idea_entry.get("team"):
            owner_formatted = format_member(idea_entry["team"][0])
        else:
            owner_formatted = idea_entry["user"]
        admin_text += f"Idea #{idx+1}: {idea_entry['idea']} (Owner: {owner_formatted})\n"
        team = idea_entry.get("team", [])
        if not team:
            admin_text += "No team members.\n"
        else:
            for member in team:
                admin_text += f"- {format_member(member)}\n"
        admin_text += "\n"
        keyboard.append([InlineKeyboardButton(
            f"Delete Idea #{idx+1}",
            callback_data=f"admindelete:{idx}"
        )])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(admin_text, reply_markup=reply_markup)

### Callback handler for inline buttons.
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split(":")
    
    if data.startswith("request:"):
        if len(parts) < 5:
            await query.edit_message_text("Invalid request data.")
            return
        idea_index = int(parts[1])
        requester_id = parts[2]
        requester_display = parts[3]
        requester_username = parts[4]
        idea_entry = ideas[idea_index]
        if int(requester_id) == idea_entry["chat_id"]:
            await query.edit_message_text("You cannot request participation in your own idea.")
            return
        creator_chat_id = idea_entry["chat_id"]
        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data=f"response:{idea_index}:{requester_id}:accept:{requester_display}:{requester_username}"),
                InlineKeyboardButton("Reject", callback_data=f"response:{idea_index}:{requester_id}:reject")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=creator_chat_id,
            text=f"User {requester_display}(@{requester_username}) has requested to participate in your idea:\n'{idea_entry['idea']}'\nDo you accept?",
            reply_markup=reply_markup
        )
        await query.edit_message_text("Your request has been sent to the idea creator.")
    
    elif data.startswith("response:"):
        if len(parts) < 4:
            await query.edit_message_text("Invalid response data.")
            return
        idea_index = int(parts[1])
        requester_id = int(parts[2])
        response = parts[3]
        idea_entry = ideas[idea_index]
        if response == "accept":
            if len(parts) < 6:
                await query.edit_message_text("Incomplete acceptance data.")
                return
            requester_display = parts[4]
            requester_username = parts[5]
            new_member = {"user_id": requester_id, "display": requester_display, "username": requester_username}
            if not any(member["user_id"] == requester_id for member in idea_entry.get("team", [])):
                idea_entry.setdefault("team", []).append(new_member)
                save_ideas()
            team_info = "Team Members:\n"
            for m in idea_entry.get("team", []):
                team_info += f"- {format_member(m)}\n"
            await context.bot.send_message(
                chat_id=requester_id,
                text=f"Your participation request for idea #{idea_index+1} was accepted. You have been added to the team.\n{team_info}"
            )
            await query.edit_message_text("You have accepted the participation request.")
        elif response == "reject":
            await context.bot.send_message(
                chat_id=requester_id,
                text=f"Your participation request for idea #{idea_index+1} was rejected."
            )
            await query.edit_message_text("You have rejected the participation request.")
        else:
            await query.edit_message_text("Unknown response.")
    
    elif data.startswith("remove:"):
        if len(parts) < 3:
            await query.edit_message_text("Invalid removal data.")
            return
        idea_index = int(parts[1])
        team_member_id = int(parts[2])
        idea_entry = ideas[idea_index]
        if not idea_entry.get("modifiable"):
            await query.edit_message_text("This idea's team cannot be modified.")
            return
        original_team = idea_entry.get("team", [])
        new_team = [member for member in original_team if member["user_id"] != team_member_id]
        if len(new_team) < len(original_team):
            idea_entry["team"] = new_team
            save_ideas()
            await context.bot.send_message(
                chat_id=team_member_id,
                text=f"You have been removed from the team for idea #{idea_index+1}: '{idea_entry['idea']}'."
            )
            await query.edit_message_text("Team member removed.")
        else:
            await query.edit_message_text("Team member not found.")
    
    elif data.startswith("admindelete:"):
        if len(parts) < 2:
            await query.edit_message_text("Invalid admin delete data.")
            return
        idea_index = int(parts[1])
        idea_entry = ideas[idea_index]
        for member in idea_entry.get("team", []):
            try:
                await context.bot.send_message(
                    chat_id=member["user_id"],
                    text=f"Admin has deleted the idea '{idea_entry['idea']}'."
                )
            except Exception:
                pass
        del ideas[idea_index]
        save_ideas()
        await query.edit_message_text("Idea deleted successfully by admin.")

async def set_bot_commands(app):
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("add_idea", "Submit an idea (use 'anonymous:' prefix for anonymous ideas)"),
        BotCommand("all_ideas", "View all ideas"),
        BotCommand("owned_teams", "View teams you created"),
        BotCommand("joined_teams", "View teams you have joined"),
        BotCommand("admin_panel", "Admin panel (use /admin_panel <password>)")
    ]
    await app.bot.set_my_commands(commands)

async def main_async():
    app = ApplicationBuilder().token(TOKEN).build()

    add_idea_conv = ConversationHandler(
        entry_points=[CommandHandler('add_idea', add_idea_command)],
        states={
            ADDING_IDEA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_idea_received)]
        },
        fallbacks=[]
    )

    admin_conv = CommandHandler('admin_panel', admin_panel)
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(add_idea_conv)
    app.add_handler(CommandHandler('all_ideas', all_ideas))
    app.add_handler(CommandHandler('owned_teams', owned_teams))
    app.add_handler(CommandHandler('joined_teams', joined_teams))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(button_handler))

    await set_bot_commands(app)
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main_async())

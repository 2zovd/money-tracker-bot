"""Entry point: build the app and start polling. Run: python -m bot.main"""
import logging

from telegram import BotCommand, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from . import access, config, dialog, store, strings

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)


async def _post_init(app):
    await app.bot.set_my_commands(
        [BotCommand(cmd, desc) for cmd, desc in strings.COMMAND_DESCRIPTIONS])


def _seed_existing_users():
    """Keep a pre-existing deployment working: the admins and the ALLOWED_USER_ID list
    are pre-approved, and if a single SHEET_ID is configured they are mapped to it once
    so they don't have to re-run onboarding."""
    for uid in config.ADMIN_USER_IDS + config.ALLOWED_USER_IDS:
        store.approve_seed(int(uid))
        if config.SHEET_ID:
            store.seed(int(uid), config.SHEET_ID)
    if not config.ADMIN_USER_IDS:
        logging.getLogger("expense-bot").warning(strings.ACCESS_NO_ADMIN_WARNING)


def main():
    config.validate()
    store.init()
    _seed_existing_users()
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", dialog.cmd_start))
    app.add_handler(CommandHandler("help", dialog.cmd_help))
    app.add_handler(CommandHandler("connect", dialog.cmd_connect))
    app.add_handler(CommandHandler("disconnect", dialog.cmd_disconnect))
    app.add_handler(CommandHandler("users", dialog.cmd_users))
    app.add_handler(CallbackQueryHandler(dialog.on_access_callback, pattern=f"^{access.CB_PREFIX}:"))
    app.add_handler(CallbackQueryHandler(dialog.on_onboarding_callback, pattern="^onb:"))
    app.add_handler(CommandHandler("day", dialog.cmd_day))
    app.add_handler(CommandHandler("week", dialog.cmd_week))
    app.add_handler(CommandHandler("month", dialog.cmd_month))
    app.add_handler(CommandHandler("category", dialog.cmd_category))
    app.add_handler(CommandHandler("months", dialog.cmd_months))
    app.add_handler(CommandHandler("income", dialog.cmd_income))
    app.add_handler(CommandHandler("debt", dialog.cmd_debt))
    app.add_handler(CommandHandler("debts", dialog.cmd_debts))
    app.add_handler(CallbackQueryHandler(dialog.on_debt_callback, pattern="^debt:"))
    app.add_handler(CommandHandler("undo", dialog.cmd_undo))
    app.add_handler(MessageHandler(filters.PHOTO, dialog.on_photo))
    app.add_handler(MessageHandler(filters.VOICE, dialog.on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dialog.on_text))
    logging.getLogger("expense-bot").info("bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

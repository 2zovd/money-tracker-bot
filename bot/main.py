"""Entry point: build the app and start polling. Run: python -m bot.main"""
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from . import config, dialog

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)


def main():
    config.validate()
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", dialog.cmd_start))
    app.add_handler(CommandHandler("help", dialog.cmd_start))
    app.add_handler(CommandHandler("day", dialog.cmd_day))
    app.add_handler(CommandHandler("week", dialog.cmd_week))
    app.add_handler(CommandHandler("month", dialog.cmd_month))
    app.add_handler(CommandHandler("income", dialog.cmd_income))
    app.add_handler(CommandHandler("undo", dialog.cmd_undo))
    app.add_handler(MessageHandler(filters.PHOTO, dialog.on_photo))
    app.add_handler(MessageHandler(filters.VOICE, dialog.on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dialog.on_text))
    logging.getLogger("expense-bot").info("bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import threads_client
import config

logger = logging.getLogger(__name__)

# Временное хранилище ожидающих ответа комментариев
# { comment_id: comment_data }
pending_replies: dict[str, dict] = {}

# Текущий комментарий, на который пишем ответ
awaiting_reply_for: dict[int, str] = {}  # { chat_id: comment_id }


async def send_notification(app: Application, text: str):
    """Отправить простое уведомление в Telegram"""
    await app.bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text)


async def send_post_notification(app: Application, post_text: str, post_id: str):
    """Уведомление об успешной публикации поста"""
    msg = (
        f"✅ *Пост опубликован в Threads*\n\n"
        f"_{post_text[:200]}{'...' if len(post_text) > 200 else ''}_\n\n"
        f"🆔 ID: `{post_id}`"
    )
    await app.bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=msg,
        parse_mode="Markdown",
    )


async def send_comment_notification(app: Application, comment: dict):
    """Отправить коммент с кнопками: Ответить / Игнорировать"""
    comment_id = comment["comment_id"]
    pending_replies[comment_id] = comment

    text = (
        f"💬 *Новый комментарий* от @{comment['username']}\n\n"
        f"*Пост:* _{comment['post_text'][:100]}..._\n\n"
        f"*Коммент:* {comment['text']}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✍️ Ответить", callback_data=f"reply:{comment_id}"),
            InlineKeyboardButton("🙈 Игнор", callback_data=f"ignore:{comment_id}"),
        ]
    ])

    await app.bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    await query.answer()

    action, comment_id = query.data.split(":", 1)

    if action == "reply":
        awaiting_reply_for[query.message.chat_id] = comment_id
        comment = pending_replies.get(comment_id, {})
        await query.edit_message_text(
            f"✍️ Пишешь ответ для @{comment.get('username', '?')}:\n\n"
            f"_{comment.get('text', '')}_\n\n"
            f"Просто отправь текст ответа:",
            parse_mode="Markdown",
        )

    elif action == "ignore":
        pending_replies.pop(comment_id, None)
        await query.edit_message_text("🙈 Проигнорировано")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Когда пользователь пишет ответ на коммент"""
    chat_id = update.message.chat_id

    if chat_id not in awaiting_reply_for:
        await update.message.reply_text(
            "Используй кнопку *✍️ Ответить* под комментарием.",
            parse_mode="Markdown",
        )
        return

    comment_id = awaiting_reply_for.pop(chat_id)
    reply_text = update.message.text

    try:
        reply_id = await threads_client.reply_to_comment(comment_id, reply_text)
        pending_replies.pop(comment_id, None)
        await update.message.reply_text(f"✅ Ответ опубликован!\nID: `{reply_id}`", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to reply: {e}")
        awaiting_reply_for[chat_id] = comment_id  # Вернуть в ожидание
        await update.message.reply_text(f"❌ Ошибка: {e}\n\nПопробуй ещё раз.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 *Бот работает*\n\n"
        f"⏱ Постинг каждые {config.POST_INTERVAL_HOURS}ч\n"
        f"🔍 Проверка комментов каждые {config.COMMENTS_CHECK_MINUTES}мин\n"
        f"💬 Ожидают ответа: {len(pending_replies)} комментариев",
        parse_mode="Markdown",
    )


async def cmd_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительно сгенерировать и опубликовать пост"""
    await update.message.reply_text("⏳ Генерирую пост...")
    # Вызов через job_queue чтобы не блокировать
    context.application.job_queue.run_once(
        lambda ctx: __import__("main").job_generate_and_post(ctx),
        when=0,
    )


def build_app() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("postnow", cmd_post_now))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

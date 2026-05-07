import asyncio
import logging
from telegram.ext import Application
import telegram_bot
import threads_client
import content_generator
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Глобальное приложение Telegram
_app: Application = None


async def job_generate_and_post(context=None):
    """Генерирует крипто-пост и публикует в Threads"""
    global _app
    logger.info("🚀 Generating new post...")
    try:
        text, image_url = await content_generator.generate_crypto_post()
        post_id = await threads_client.create_post(text, image_url)

        if _app:
            await telegram_bot.send_post_notification(_app, text, post_id)

        logger.info(f"✅ Post published: {post_id}")
    except Exception as e:
        logger.error(f"❌ Post failed: {e}")
        if _app:
            await telegram_bot.send_notification(_app, f"❌ Ошибка постинга: {e}")


async def job_check_comments(context=None):
    """Проверяет новые комменты и форвардит в Telegram"""
    global _app
    logger.info("🔍 Checking comments...")
    try:
        new_comments = await threads_client.get_new_comments()
        for comment in new_comments:
            logger.info(f"New comment from @{comment['username']}: {comment['text'][:50]}")
            if _app:
                await telegram_bot.send_comment_notification(_app, comment)
    except Exception as e:
        logger.error(f"❌ Comment check failed: {e}")


async def main():
    global _app

    logger.info("Starting Crypto Autopost Bot...")

    # Создаём Telegram приложение
    _app = telegram_bot.build_app()

    # Добавляем периодические задачи через job_queue
    job_queue = _app.job_queue

    # Постить каждые N часов
    job_queue.run_repeating(
        job_generate_and_post,
        interval=config.POST_INTERVAL_HOURS * 3600,
        first=10,  # Первый пост через 10 секунд после старта
        name="auto_post",
    )

    # Проверять комменты каждые N минут
    job_queue.run_repeating(
        job_check_comments,
        interval=config.COMMENTS_CHECK_MINUTES * 60,
        first=30,
        name="check_comments",
    )

    logger.info(
        f"✅ Bot started\n"
        f"   Posts every: {config.POST_INTERVAL_HOURS}h\n"
        f"   Comment checks every: {config.COMMENTS_CHECK_MINUTES}min"
    )

    # Запускаем бота (polling)
    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling()

    # Держим живым
    try:
        await asyncio.Event().wait()
    finally:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

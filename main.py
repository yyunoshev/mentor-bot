import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from motor.motor_asyncio import AsyncIOMotorClient
import openai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/bot.log') if os.path.exists('/app/logs/bot.log') else logging.StreamHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Проверка обязательных переменных окружения
if BOT_TOKEN == "":
    logger.error("❌ BOT_TOKEN не установлен! Задайте переменную окружения BOT_TOKEN")
    exit(1)

if OPENAI_API_KEY == "":
    logger.error("❌ OPENAI_API_KEY не установлен! Задайте переменную окружения OPENAI_API_KEY")
    exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

openai.api_key = OPENAI_API_KEY

mongo_client = AsyncIOMotorClient(MONGODB_URL)
db = mongo_client[DATABASE_NAME]
users_collection = db.users
chats_collection = db.chats


class BotStates(StatesGroup):
    waiting_for_topic = State()
    chatting = State()




class User:
    def __init__(self, user_id: int, username: str = None, topic: str = None, notification_interval: int = None, last_message_time: datetime = None):
        self.user_id = user_id
        self.username = username
        self.topic = topic
        self.notification_interval = notification_interval
        self.last_message_time = last_message_time


class ChatMessage:
    def __init__(self, user_id: int, role: str, content: str, timestamp: datetime = None):
        self.user_id = user_id
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()



async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        return await users_collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя: {user_id}: {e}")


async def create_or_update_user(user_data: Dict[str, Any]) -> None:
    try:
        await users_collection.update_one(
            {"user_id": user_data["user_id"]},
            {"$set": user_data},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользователя: {e}")



async def get_chat_history(user_id: int, limit: int = 50) -> list:
    try:
        cursor = chats_collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)

        messages = []
        async for message in cursor:
            messages.append({
                "role": message["role"],
                "content": message["content"],
            })
        return list(reversed(messages))
    except Exception as e:
        logger.error(f"Ошибка при получении истории чата для пользователя {user_id}: {e}")
        return []



async def save_message(user_id:int , role: str, content: str) -> None:
    try:
        message_data = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        }
        await chats_collection.insert_one(message_data)
    except Exception as e:
        logger.error(f"Ошибка при сохранении сообщения: {e}")


async def clear_chat_history(user_id: int) -> None:
    try:
        await chats_collection.delete_many({"user_id": user_id})
    except Exception as e:
        logger.error(f"Ошибка при очистке истории чата для пользователя {user_id}: {e}")



async def get_chatgpt_response(user_id: int, user_message: str, topic: str = None) -> str:
    try:
        chat_history = await get_chat_history(user_id)
        messages = []

        if topic:
            system_message = f"Ты помощник, который ведет беседу на тему: '{topic}'. Поддерживай разговор в рамках этой темы и помогай пользователю достигать его целей."
            messages.append({"role": "system", "content": system_message})


        messages.extend(chat_history)

        messages.append({"role": "user", "content": user_message})

        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Ошибка при обращении к OpenAI: {e}")
        return f"Сорян, произошла ошибка при обращении к GPT:\n{e}"


def get_start_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить тему", callback_data="update_topic")],
        [InlineKeyboardButton(text="❌ Игнорировать", callback_data="ignore_start")]
    ])
    return keyboard


def get_notification_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора интервала уведомлений"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Каждый час", callback_data="notify_1")],
        [InlineKeyboardButton(text="⏰ Каждые 3 часа", callback_data="notify_3")],
        [InlineKeyboardButton(text="⏰ Каждые 6 часов", callback_data="notify_6")],
        [InlineKeyboardButton(text="⏰ Каждые 12 часов", callback_data="notify_12")],
        [InlineKeyboardButton(text="❌ Отключить уведомления", callback_data="notify_off")]
    ])
    return keyboard


@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username

    user = await get_user(user_id)

    if not user or not user.get("topic"):
        await message.answer(
            "👋 Привет! Я AI-бот для общения.\n\n"
            "📝 Задай тему для нашего общения:"
        )
        await state.set_state(BotStates.waiting_for_topic)

        user_data = {
            "user_id": user_id,
            "username": username,
            "topic": None,
            "notification_interval": None,
            "last_message_time": datetime.now()
        }
        await create_or_update_user(user_data)

    else:
        await message.answer(
            f"🤔 У вас уже есть активная тема: '{user['topic']}'\n\n"
            "Что вы хотите сделать?",
            reply_markup=get_start_keyboard()
        )


@dp.message(Command("restart"))
async def restart_command(message: Message, state: FSMContext):
    user_id = message.from_user.id

    await clear_chat_history(user_id)

    await message.answer(
        "🔄 Давайте начнем заново!\n\n"
        "📝 Задай новую тему для нашего общения:"
    )
    await state.set_state(BotStates.waiting_for_topic)


@dp.message(Command("notify"))
async def notify_command(message: Message):
    """Обработчик команды /notify"""
    await message.answer(
        "🔔 Настройка уведомлений\n\n"
        "Выберите, как часто вы хотите получать напоминания о ваших целях:",
        reply_markup=get_notification_keyboard()
    )


@dp.message(Command("status"))
async def status_command(message: Message):
    """Обработчик команды /status - показать статус бота и пользователя"""
    user_id = message.from_user.id
    user = await get_user(user_id)

    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start для начала работы.")
        return

    # Подсчитываем количество сообщений
    message_count = await chats_collection.count_documents({"user_id": user_id})

    status_text = f"""📊 **Статус вашего профиля:**
        👤 **Пользователь:** {user.get('username', 'Не указан')}
        🎯 **Тема:** {user.get('topic', 'Не выбрана')}
        💬 **Сообщений:** {message_count}
        🔔 **Уведомления:** {'Каждые ' + str(user.get('notification_interval', 0)) + ' ч.' if user.get('notification_interval') else 'Отключены'}
        ⏰ **Последнее сообщение:** {user.get('last_message_time', 'Неизвестно')}
        
        **Доступные команды:**
        /start - Начать или изменить тему
        /restart - Начать заново
        /notify - Настроить уведомления
        /status - Показать этот статус"""

    await message.answer(status_text, parse_mode="Markdown")

# Обработчики callback-запросов
@dp.callback_query(F.data == "update_topic")
async def update_topic_callback(callback: CallbackQuery, state: FSMContext):
    """Обновление темы"""
    await callback.message.edit_text(
        "🔄 Хорошо, давайте обновим тему!\n\n"
        "📝 Задай новую тему для нашего общения:"
    )
    await state.set_state(BotStates.waiting_for_topic)
    await callback.answer()


@dp.callback_query(F.data == "ignore_start")
async def ignore_start_callback(callback: CallbackQuery, state: FSMContext):
    """Игнорирование команды /start"""
    await state.set_state(BotStates.chatting)
    await callback.message.edit_text("✅ Команда проигнорирована. Продолжаем общение!")
    await callback.answer()


@dp.callback_query(F.data.startswith("notify_"))
async def notification_callback(callback: CallbackQuery):
    """Настройка уведомлений"""
    user_id = callback.from_user.id
    action = callback.data.split("_")[1]

    if action == "off":
        # Отключаем уведомления
        await create_or_update_user({
            "user_id": user_id,
            "notification_interval": None
        })
        await callback.message.edit_text("❌ Уведомления отключены")

        # Удаляем задачу из планировщика
        try:
            scheduler.remove_job(f"notify_{user_id}")
        except:
            pass

    else:
        # Настраиваем уведомления
        interval = int(action)
        await create_or_update_user({
            "user_id": user_id,
            "notification_interval": interval
        })

        await callback.message.edit_text(
            f"✅ Уведомления настроены на каждые {interval} час(а/ов)"
        )

        # Настраиваем задачу в планировщике
        setup_notification_job(user_id, interval)

    await callback.answer()


# Обработчик состояния ожидания темы
@dp.message(StateFilter(BotStates.waiting_for_topic))
async def handle_topic_input(message: Message, state: FSMContext):
    """Обработка ввода темы"""
    user_id = message.from_user.id
    topic = message.text.strip()

    if len(topic) < 3:
        await message.answer("❌ Тема слишком короткая. Пожалуйста, введите более подробную тему.")
        return

    # Сохраняем тему в базу данных
    await create_or_update_user({
        "user_id": user_id,
        "topic": topic,
        "last_message_time": datetime.now()
    })

    # Очищаем историю чата для новой темы
    await clear_chat_history(user_id)

    # Сохраняем первое сообщение (тему) в историю
    msg = f"Я хочу поговорить с тобой на тему: '{topic}'. Будь краток, убедителен, жесток по отношению к правде. Мне нужно, чтобы ты не нянчился со мной, а помог мне достичь цели. Я хочу, чтобы ты матерился для пущего эффекта. Твоя задача давать мне пендели, а не пряники"
    await save_message(user_id, "user", msg)

    # Получаем ответ от ChatGPT
    response = await get_chatgpt_response(user_id, topic, topic)

    # Сохраняем ответ
    await save_message(user_id, "assistant", response)

    await message.answer(
        f"✅ Отлично! Тема установлена: '{topic}'\n\n"
        f"🤖 {response}"
    )

    await state.set_state(BotStates.chatting)


# Обработчик обычных сообщений
@dp.message(StateFilter(BotStates.chatting))
async def handle_chat_message(message: Message):
    """Обработка обычных сообщений в чате"""
    user_id = message.from_user.id
    user_message = message.text

    # Получаем пользователя
    user = await get_user(user_id)
    if not user or not user.get("topic"):
        await message.answer("❌ Сначала выберите тему с помощью команды /start")
        return

    # Обновляем время последнего сообщения
    await create_or_update_user({
        "user_id": user_id,
        "last_message_time": datetime.now()
    })

    # Сохраняем сообщение пользователя
    await save_message(user_id, "user", user_message)

    # Получаем ответ от ChatGPT
    response = await get_chatgpt_response(user_id, user_message, user["topic"])

    # Сохраняем ответ
    await save_message(user_id, "assistant", response)

    await message.answer(response)


@dp.message()
async def handle_other_messages(message: Message, state: FSMContext):
    """Обработчик всех остальных сообщений"""
    user_id = message.from_user.id
    user = await get_user(user_id)

    # Если пользователь существует и у него есть тема, переводим в состояние чата
    if user and user.get("topic"):
        await state.set_state(BotStates.chatting)
        # Обрабатываем сообщение как обычное сообщение в чате
        await handle_chat_message(message)
        return

    # Если пользователя нет или нет темы, показываем справку
    await message.answer(
        "🤔 Я не понимаю это сообщение.\n\n"
        "Используйте:\n"
        "▫️ /start - начать общение\n"
        "▫️ /restart - начать заново\n"
        "▫️ /notify - настроить уведомления\n"
        "▫️ /status - показать статус"
    )

# Функции для уведомлений
def setup_notification_job(user_id: int, interval_hours: int):
    """Настройка задачи уведомлений"""
    job_id = f"notify_{user_id}"

    # Удаляем существующую задачу, если есть
    try:
        scheduler.remove_job(job_id)
    except:
        pass

    # Добавляем новую задачу
    scheduler.add_job(
        send_notification,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[user_id],
        id=job_id,
        replace_existing=True
    )

    logger.info(f"Настроена задача уведомлений для пользователя {user_id} каждые {interval_hours} часов")


async def send_notification(user_id: int):
    """Отправка уведомления пользователю"""
    try:
        user = await get_user(user_id)
        if not user or not user.get("notification_interval"):
            return

        # Проверяем, прошло ли достаточно времени с последнего сообщения
        if user.get("last_message_time"):
            time_diff = datetime.now() - user["last_message_time"]
            required_interval = timedelta(hours=user["notification_interval"])

            if time_diff >= required_interval:
                # Отправляем напоминание через ChatGPT
                reminder_message = "Напомни мне о моих целях. Замотивируй меня или напомни о дисциплине. Не пиши 'Хорошо и тд тп'. Просто жестко по фактам раскидай что будет, если я буду дальше ебланить и что будет со мной, если я буду продолжать ебашить на протяжении нескольких месяцев или лет. Возможно нужно сравнение"
                response = await get_chatgpt_response(user_id, reminder_message, user["topic"])

                # Сохраняем в историю
                await save_message(user_id, "user", reminder_message)
                await save_message(user_id, "assistant", response)

                # Отправляем уведомление
                await bot.send_message(
                    user_id,
                    f"🔔 Напоминание о ваших целях:\n\n{response}"
                )

                # Обновляем время последнего сообщения
                await create_or_update_user({
                    "user_id": user_id,
                    "last_message_time": datetime.now()
                })

                logger.info(f"Отправлено уведомление пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")


# Функция проверки подключения к базе данных
async def check_database_connection():
    """Проверка подключения к MongoDB"""
    try:
        # Проверяем подключение
        await mongo_client.admin.command('ping')
        logger.info("✅ Подключение к MongoDB успешно")

        # Проверяем существование базы данных
        db_list = await mongo_client.list_database_names()
        if DATABASE_NAME in db_list:
            logger.info(f"✅ База данных '{DATABASE_NAME}' найдена")
        else:
            logger.warning(f"⚠️ База данных '{DATABASE_NAME}' не найдена, будет создана автоматически")

        return True
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к MongoDB: {e}")
        return False


# Основная функция
async def main():
    """Основная функция запуска бота"""
    try:
        logger.info("🚀 Запуск AI Telegram Bot...")

        # Проверяем подключение к базе данных
        if not await check_database_connection():
            logger.error("❌ Не удалось подключиться к базе данных")
            return

        # Запускаем планировщик
        scheduler.start()
        logger.info("✅ Планировщик задач запущен")

        # Восстанавливаем задачи уведомлений для существующих пользователей
        async for user in users_collection.find({"notification_interval": {"$ne": None}}):
            setup_notification_job(user["user_id"], user["notification_interval"])

        logger.info("✅ Задачи уведомлений восстановлены")
        logger.info("🤖 Бот готов к работе!")

        # Запускаем polling
        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        logger.info("🔄 Завершение работы...")
        scheduler.shutdown()
        await bot.session.close()
        mongo_client.close()
        logger.info("👋 Бот остановлен")


if __name__ == "__main__":
    # Создаем директорию для логов, если её нет
    os.makedirs('/app/logs', exist_ok=True)

    # Запускаем бота
    asyncio.run(main())
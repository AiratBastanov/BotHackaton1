import logging
import asyncio
import os
import sys
from io import BytesIO
from dotenv import load_dotenv

# Загружаем переменные окружения ПЕРВЫМ ДЕЛОМ
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

print("🚀 Запуск AI Telegram Bot с УЛЬТРА-фильтрацией...")

try:
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    import aiohttp
    from utils.text_filter import text_filter
    from utils.context_manager import ContextManager
    from utils.voice_processor import voice_processor
    
    # Пробуем импортировать плагины
    try:
        from plugins.init import plugin_manager
        PLUGINS_AVAILABLE = True
        print("✅ Все импорты успешны")
    except ImportError as e:
        PLUGINS_AVAILABLE = False
        print(f"⚠️  Плагины недоступны: {e}")
        print("⚠️  Бот запустится без плагинов погоды и курса валют")

except ImportError as e:
    logger.error(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

# Инициализация компонентов
context_manager = ContextManager()

class DeepSeekAI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    async def generate_response(self, messages: list) -> str:
        """Генерация ответа через DeepSeek API с retry логикой"""
        return await self._generate_response_with_retry(messages)

    async def _generate_response_with_retry(self, messages: list) -> str:
        """Версия с retry логикой"""
        if not self.api_key or self.api_key == "your_actual_deepseek_api_key_here":
            return "❌ API ключ DeepSeek не настроен. Пожалуйста, установите DEEPSEEK_API_KEY в .env файле."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False
        }

        # Retry логика
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                            self.api_url,
                            headers=headers,
                            json=payload,
                            timeout=60
                    ) as response:

                        if response.status == 200:
                            data = await response.json()
                            return data["choices"][0]["message"]["content"]
                        else:
                            error_text = await response.text()
                            logger.error(f"DeepSeek API error (attempt {attempt + 1}): {error_text}")
                            
                            if attempt == 2:  # Последняя попытка
                                return "Извините, произошла ошибка при обработке запроса."
                            await asyncio.sleep(2 ** attempt)  # Экспоненциальная backoff

            except asyncio.TimeoutError:
                logger.error(f"DeepSeek API timeout (attempt {attempt + 1})")
                if attempt == 2:
                    return "Извините, время ожидания ответа истекло. Попробуйте еще раз."
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"DeepSeek API exception (attempt {attempt + 1}): {e}")
                if attempt == 2:
                    return "Извините, произошла непредвиденная ошибка."
                await asyncio.sleep(2 ** attempt)

        return "Извините, не удалось обработать запрос после нескольких попыток."


# Инициализация AI
ai_agent = DeepSeekAI(os.getenv("DEEPSEEK_API_KEY"))

class FileProcessor:
    """Класс для обработки файлов"""

    @staticmethod
    async def extract_text_from_pdf(file_content: bytes) -> str:
        """Извлечение текста из PDF с помощью PyPDF2"""
        try:
            import PyPDF2
            with BytesIO(file_content) as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except ImportError:
            raise Exception("PyPDF2 не установлен. Установите: pip install PyPDF2")
        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            raise Exception(f"Ошибка чтения PDF: {e}")

    @staticmethod
    async def extract_text_from_docx(file_content: bytes) -> str:
        """Извлечение текста из DOCX с помощью python-docx"""
        try:
            from docx import Document
            with BytesIO(file_content) as file:
                doc = Document(file)
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                return text.strip()
        except ImportError:
            raise Exception("python-docx не установлен. Установите: pip install python-docx")
        except Exception as e:
            logger.error(f"DOCX extraction error: {e}")
            raise Exception(f"Ошибка чтения DOCX: {e}")

    @staticmethod
    async def extract_text_from_txt(file_content: bytes) -> str:
        """Извлечение текста из TXT"""
        try:
            # Пробуем разные кодировки
            encodings = ['utf-8', 'cp1251', 'windows-1251', 'iso-8859-1']

            for encoding in encodings:
                try:
                    text = file_content.decode(encoding)
                    return text.strip()
                except UnicodeDecodeError:
                    continue

            # Если ни одна кодировка не подошла
            raise UnicodeDecodeError("Не удалось декодировать файл")

        except Exception as e:
            logger.error(f"TXT extraction error: {e}")
            raise Exception(f"Ошибка чтения TXT файла: {e}")

    @staticmethod
    async def analyze_text_with_ai(text: str, analysis_type: str = "summary") -> str:
        """Анализ текста с помощью AI"""
        prompts = {
            "summary": "Сделай краткий пересказ этого текста, выдели основные идеи и ключевые моменты. Будь лаконичным:",
            "key_points": "Выдели ключевые пункты и основные мысли из этого текста в виде маркированного списка:",
            "analysis": "Проанализируй этот текст и дай развернутый анализ основных тем и идей:",
            "qa": "Составь 3-5 самых важных вопросов по содержанию этого текста и дай на них краткие ответы:"
        }

        prompt = prompts.get(analysis_type, prompts["summary"])

        messages = [
            {
                "role": "system",
                "content": "Ты эксперт по анализу текстов. Ты делаешь качественные анализы, пересказы и выделяешь ключевые моменты. Будь информативным, но лаконичным."
            },
            {
                "role": "user",
                "content": f"{prompt}\n\nТекст для анализа:\n{text[:15000]}"  # Ограничиваем длину
            }
        ]

        return await ai_agent.generate_response(messages)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start с кнопками"""
    user = update.effective_user
    user_context = context_manager.get_user_context(user.id)
    user_context.user_name = user.first_name

    # Создаем клавиатуру с кнопками (адаптивная в зависимости от доступности плагинов)
    if PLUGINS_AVAILABLE:
        keyboard = [
            [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
            [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
            [KeyboardButton("📊 Анализ файлов"), KeyboardButton("🌤️ Погода"), KeyboardButton("💱 Курсы валют")]
        ]
    else:
        keyboard = [
            [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
            [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
            [KeyboardButton("📊 Анализ файлов")]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # ВЫНОСИМ ПЕРЕМЕННУЮ ВНЕ F-СТРОКИ
    plugins_addition = "• Прогноз погоды\n• Курсы валют" if PLUGINS_AVAILABLE else ""

    welcome_text = f"""
Привет, {user.first_name}! 👋

🤖 Я AI-ассистент с ПРОДВИНУТОЙ системой модерации:

🛡️ АКТИВНАЯ ЗАЩИТА:
• Детекция нецензурной лексики
• Блокировка ссылок и контактов  
• Анти-спам фильтр
• Защита от мошенничества
• Контент-фильтрация

📝 Анализ документов:
• 📄 PDF файлы
• 📝 DOCX документы  
• 📃 TXT текстовые файлы

🎤 Новые возможности:
• Голосовые сообщения
{plugins_addition}
💬 Безопасное общение гарантировано!
    """

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    logger.info(f"User {user.id} started conversation")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    # ВЫНОСИМ ПЕРЕМЕННУЮ ВНЕ F-СТРОКИ
    plugins_text = ""
    if PLUGINS_AVAILABLE:
        plugins_text = "• 🌤️ Прогноз погоды (/weather)\n• 💱 Курсы валют (/currency)\n"

    help_text = f"""
🤖 Помощь по боту

🛡️ Система безопасности РАБОТАЕТ:
• Автоматическая блокировка нарушений
• Умное распознавание контента
• Мгновенная реакция на спам
• Защита данных пользователей

Основные функции:
• 📄 Анализ PDF/DOCX/TXT файлов
• 🎤 Обработка голосовых сообщений
{plugins_text}
• 💬 Умный диалог с AI

Нарушения блокируются автоматически!
    """

    await update.message.reply_text(help_text)


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /about"""
    about_text = """
🤖 AI Telegram Bot с АКТИВНОЙ цензурой

Технологии защиты:
• Многоуровневый анализ текста
• Распознавание скрытых нарушений
• Контекстная оценка содержания
• Поведенческий анализ

Новые возможности:
• Retry-логика для надежности API
• Обработка голосовых сообщений

Гарантируем безопасное общение!
    """

    await update.message.reply_text(about_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    user = update.effective_user
    user_context = context_manager.get_user_context(user.id)
    user_context.reset()

    await update.message.reply_text("✅ История разговора сброшена. Начнем новый диалог!")
    logger.info(f"User {user.id} reset conversation")


async def show_examples(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать примеры запросов"""
    # ВЫНОСИМ ПЕРЕМЕННУЮ ВНЕ F-СТРОКИ
    plugins_examples = ""
    if PLUGINS_AVAILABLE:
        plugins_examples = "Команды:\n• /weather - прогноз погоды\n• /currency - Курсы валют\n• /help - помощь\n"

    examples_text = f"""
💡 Примеры РАЗРЕШЕННЫХ запросов:

Для файлов:
Отправьте PDF/DOCX/TXT файл для анализа

Голосовые сообщения:
Отправьте голосовое сообщение - я распознаю текст!

{plugins_examples}
Вопросы к AI:
• "Напиши план обучения Python"
• "Объясни теорию относительности" 
• "Помоги с кодом для сортировки"

🚫 АВТОМАТИЧЕСКИ БЛОКИРУЕТСЯ:
• Любая нецензурная лексика
• Ссылки и контактные данные
• Рекламный и спам-контент
• Мошеннические схемы
    """
    await update.message.reply_text(examples_text, parse_mode='Markdown')


async def show_file_analysis_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать варианты анализа файлов"""
    options_text = """
📊 Анализ документов

Отправьте файл в одном из форматов:
• 📄 PDF документы
• 📝 DOCX документы  
• 📃 TXT текстовые файлы

🛡️ ВСЕ файлы проверяются на нарушения!
    """
    await update.message.reply_text(options_text, parse_mode='Markdown')


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик файлов"""
    user = update.effective_user
    file = await update.message.document.get_file()

    # Проверка размера файла
    if file.file_size > 20 * 1024 * 1024:  # 20MB
        await update.message.reply_text("❌ Файл слишком большой (макс. 20MB)")
        return

    file_name = update.message.document.file_name.lower()
    file_extension = os.path.splitext(file_name)[1]

    supported_formats = ['.pdf', '.docx', '.txt']
    if file_extension not in supported_formats:
        await update.message.reply_text("❌ Неподдерживаемый формат. Используйте PDF, DOCX или TXT")
        return

    await update.message.reply_text("📥 Загружаю файл...")

    try:
        # Скачиваем файл
        file_content = await file.download_as_bytearray()

        # Определяем тип файла и извлекаем текст
        if file_extension == '.pdf':
            extracted_text = await FileProcessor.extract_text_from_pdf(file_content)
            file_type = "PDF"
        elif file_extension == '.docx':
            extracted_text = await FileProcessor.extract_text_from_docx(file_content)
            file_type = "DOCX"
        elif file_extension == '.txt':
            extracted_text = await FileProcessor.extract_text_from_txt(file_content)
            file_type = "TXT"

        if not extracted_text:
            await update.message.reply_text("❌ Не удалось извлечь текст из файла")
            return

        # УСИЛЕННАЯ ПРОВЕРКА ТЕКСТА ФАЙЛА
        filtered_text, error = text_filter.filter_text(extracted_text)
        if error:
            error_parts = error.split(": ")
            if len(error_parts) == 2:
                error_type, error_detail = error_parts
            else:
                error_type, error_detail = "нарушение", error

            await update.message.reply_text(
                f"🚫 Файл заблокирован\n"
                f"Причина: {error_detail}\n\n"
                f"Отправьте другой файл."
            )
            logger.warning(f"File blocked for user {user.id}: {error}")
            return

        # Сохраняем текст в контексте для дальнейшего анализа
        user_context = context_manager.get_user_context(user.id)
        user_context.current_file_text = extracted_text
        user_context.current_file_type = file_type

        # Показываем варианты анализа
        analysis_keyboard = [
            [KeyboardButton("📋 Пересказ"), KeyboardButton("🔑 Ключевые пункты")],
            [KeyboardButton("📊 Подробный анализ"), KeyboardButton("❓ Вопросы и ответы")],
            [KeyboardButton("◀️ Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(analysis_keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"✅ Файл загружен ({file_type})\n"
            f"📏 Текст: {len(extracted_text)} символов\n"
            f"🛡️ Проверка: ✅ Безопасно\n\n"
            f"Выберите тип анализа:",
            reply_markup=reply_markup
        )

        logger.info(f"File {file_name} processed for user {user.id}")

    except Exception as e:
        logger.error(f"File processing error: {e}")
        await update.message.reply_text("❌ Ошибка обработки файла")


async def handle_analysis_request(update: Update, context: ContextTypes.DEFAULT_TYPE, analysis_type: str):
    """Обработка запроса анализа"""
    user = update.effective_user
    user_context = context_manager.get_user_context(user.id)

    if not hasattr(user_context, 'current_file_text') or not user_context.current_file_text:
        await update.message.reply_text("❌ Нет текста для анализа. Сначала отправьте файл.")
        return

    await update.message.reply_text("🤔 Анализирую...")
    await update.message.chat.send_action(action="typing")

    try:
        analysis_result = await FileProcessor.analyze_text_with_ai(
            user_context.current_file_text,
            analysis_type
        )

        # Добавляем заголовок в зависимости от типа анализа
        analysis_titles = {
            "summary": "📋 Краткий пересказ",
            "key_points": "🔑 Ключевые пункты",
            "analysis": "📊 Подробный анализ",
            "qa": "❓ Вопросы и ответы"
        }

        title = analysis_titles.get(analysis_type, "📊 Результат анализа")

        await update.message.reply_text(f"{title}:\n\n{analysis_result}")
        logger.info(f"Analysis completed for user {user.id}, type: {analysis_type}")

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        await update.message.reply_text("❌ Ошибка анализа")


async def _is_confused_response(response: str) -> bool:
    """Проверяет, указывает ли ответ AI на непонимание запроса"""
    confusion_indicators = [
        "не совсем понял", "не понимаю", "уточните",
        "повторите", "конкретнее", "could you clarify",
        "can you explain", "not sure what you mean",
        "не ясно", "не понял вопрос"
    ]

    response_lower = response.lower()
    return any(indicator in response_lower for indicator in confusion_indicators)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """УЛЬТРА-обработчик текстовых сообщений с АКТИВНОЙ фильтрацией"""
    user = update.effective_user
    user_message = update.message.text

    logger.info(f"Received message from {user.id}: {user_message}")

    # ПЕРВОЕ: Проверяем, не является ли это вводом города для погоды
    if PLUGINS_AVAILABLE:
        try:
            weather_plugin = plugin_manager.get_plugin("weather")
            if weather_plugin and weather_plugin.is_initialized():
                user_data = weather_plugin.get_user_data(user.id)
                if user_data.get('awaiting_city_input'):
                    # Проверяем, что введенный текст похож на название города
                    if (len(user_message) < 50 and 
                        all(c.isalpha() or c.isspace() or c in '-,.' for c in user_message) and
                        len(user_message.strip()) > 1):
                        
                        logger.info(f"Processing city input in main handler: {user_message}")
                        await weather_plugin._process_city_input(update, user_message.strip(), user.id)
                        return
                    else:
                        # Если текст не похож на город, сбрасываем флаг и показываем сообщение
                        user_data['awaiting_city_input'] = False
                        weather_plugin.set_user_data(user.id, user_data)
                        await update.message.reply_text(
                            "❌ Это не похоже на название города. Попробуйте еще раз или выберите город из списка."
                        )
                        await weather_plugin._show_city_selection(update)
                        return
        except Exception as e:
            logger.error(f"Error checking weather plugin city input: {e}")

    # Обработка кнопок основного меню (только основные кнопки, не плагины)
    button_handlers = {
        "❓ Помощь": help_command,
        "ℹ️ О боте": about_command,
        "🔄 Сбросить диалог": reset_command,
        "💡 Примеры запросов": show_examples,
        "📊 Анализ файлов": show_file_analysis_options,
        "📋 Пересказ": lambda u, c: handle_analysis_request(u, c, "summary"),
        "🔑 Ключевые пункты": lambda u, c: handle_analysis_request(u, c, "key_points"),
        "📊 Подробный анализ": lambda u, c: handle_analysis_request(u, c, "analysis"),
        "❓ Вопросы и ответы": lambda u, c: handle_analysis_request(u, c, "qa")
    }

    # Обработка обычных кнопок меню
    if user_message in button_handlers:
        try:
            await button_handlers[user_message](update, context)
        except Exception as e:
            logger.error(f"Error handling button {user_message}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке команды. Попробуйте еще раз."
            )
        return

    # Кнопка возврата в главное меню
    if user_message == "◀️ Назад":
        if PLUGINS_AVAILABLE:
            keyboard = [
                [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
                [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
                [KeyboardButton("📊 Анализ файлов"), KeyboardButton("🌤️ Погода"), KeyboardButton("💱 Курсы валют")]
            ]
        else:
            keyboard = [
                [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
                [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
                [KeyboardButton("📊 Анализ файлов")]
            ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=reply_markup)
        return

    # УСИЛЕННАЯ ФИЛЬТРАЦИЯ СООБЩЕНИЯ
    filtered_message, error = text_filter.filter_text(user_message)
    if error:
        logger.warning(f"Message BLOCKED for user {user.id}: {error}")

        # Разбираем ошибку на тип и детали
        error_parts = error.split(": ")
        if len(error_parts) == 2:
            error_type, error_detail = error_parts
        else:
            error_type, error_detail = "нарушение", error

        # КРАТКИЕ И ПОНЯТНЫЕ УВЕДОМЛЕНИЯ О БЛОКИРОВКЕ
        block_messages = {
            "нецензурная лексика": "🚫 Обнаружена нецензурная лексика",
            "ссылки/контакты": "🔗 Запрещены ссылки и контакты",
            "рекламный спам": "📢 Заблокирован рекламный спам",
            "мошенничество": "🎭 Обнаружены признаки мошенничества",
            "взрослый контент": "🔞 Неподходящий контент",
            "контент о насилии": "⚔️ Заблокирован контент о насилии",
            "наркотики": "💊 Обнаружены упоминания наркотиков",
            "разжигание ненависти": "💀 Заблокирован опасный контент",
            "капслок": "🔊 Сообщение написано капсом",
            "повторения": "🔄 Слишком много повторений",
            "пунктуация": "❗ Избыточная пунктуация",
            "личные данные": "📋 Обнаружены личные данные",
            "флуд": "💬 Обнаружен флуд",
            "спецсимволы": "🔣 Слишком много спецсимволов"
        }

        # Выбираем сообщение об ошибке
        block_message = block_messages.get(error_type, "🚫 Сообщение нарушает правила")

        await update.message.reply_text(
            f"{block_message}\n\n"
            f"Переформулируйте запрос."
        )
        return

    # Проверка на неясные запросы
    if text_filter.is_unclear_message(filtered_message):
        await update.message.reply_text(
            "🤔 Не совсем понял ваш запрос.\n\n"
            "Сформулируйте конкретнее или нажмите '💡 Примеры запросов'"
        )
        return

    # Обработка РАЗРЕШЕННОГО сообщения
    user_context = context_manager.get_user_context(user.id)
    user_context.add_message("user", filtered_message)

    await update.message.chat.send_action(action="typing")

    try:
        conversation_history = user_context.get_conversation_history()

        system_prompt = {
            "role": "system",
            "content": """Ты полезный AI-ассистент в Telegram боте. 
            Отвечай дружелюбно и информативно. 
            Если вопрос непонятен - вежливо попроси уточнить.
            Будь краток, но содержателен. Используй эмодзи где уместно."""
        }

        messages = [system_prompt] + conversation_history

        ai_response = await ai_agent.generate_response(messages)

        if await _is_confused_response(ai_response):
            await update.message.reply_text(
                "🤔 Не совсем понял запрос.\n\n"
                "Можете переформулировать?"
            )
            return

        user_context.add_message("assistant", ai_response)
        await update.message.reply_text(ai_response)
        logger.info(f"Sent AI response to {user.id}")

    # В handle_message добавьте:
    except asyncio.TimeoutError:
        await update.message.reply_text("⏰ AI сервис временно недоступен. Попробуйте позже.")
    except Exception as e:
        logger.error(f"AI processing failed: {e}")
        await update.message.reply_text("❌ Ошибка обработки запроса. Попробуйте еще раз.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик голосовых сообщений"""
    await update.message.reply_text("🎤 Обрабатываю голосовое сообщение...")
    
    try:
        voice_file = await update.message.voice.get_file()
        voice_content = await voice_file.download_as_bytearray()
        
        result = await voice_processor.process_voice_message(voice_content)
        
        if result["success"]:
            await update.message.reply_text(
                f"🎤 Распознанный текст:\n{result['text']}\n\n"
                f"Теперь обрабатываю ваш запрос..."
            )
            
            # Обрабатываем распознанный текст как обычное сообщение
            user = update.effective_user
            user_context = context_manager.get_user_context(user.id)
            user_context.add_message("user", result['text'])

            await update.message.chat.send_action(action="typing")

            try:
                conversation_history = user_context.get_conversation_history()

                system_prompt = {
                    "role": "system",
                    "content": """Ты полезный AI-ассистент в Telegram боте. 
                    Отвечай дружелюбно и информативно. 
                    Если вопрос непонятен - вежливо попроси уточнить.
                    Будь краток, но содержателен. Используй эмодзи где уместно."""
                }

                messages = [system_prompt] + conversation_history

                ai_response = await ai_agent.generate_response(messages)

                if await _is_confused_response(ai_response):
                    await update.message.reply_text(
                        "🤔 Не совсем понял ваш голосовой запрос.\n\n"
                        "Можете переформулировать или написать текст?"
                    )
                    return

                user_context.add_message("assistant", ai_response)
                await update.message.reply_text(ai_response)
                logger.info(f"Sent AI response to {user.id} (from voice)")

            except Exception as e:
                logger.error(f"Error processing voice message text: {e}")
                await update.message.reply_text("❌ Ошибка обработки распознанного текста.")
            
        else:
            await update.message.reply_text(
                "❌ Не удалось распознать речь. Попробуйте говорить четче или напишите текст."
            )
            
    except Exception as e:
        logger.error(f"Voice handling error: {e}")
        logger.exception("Full voice error details:")
        await update.message.reply_text("❌ Ошибка обработки голосового сообщения.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик изображений"""
    await update.message.reply_text(
        "🖼️ Распознавание текста с изображений недоступно.\n\n"
        "Отправьте текстовые файлы (PDF/DOCX/TXT) или напишите вопрос."
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок с улучшенной диагностикой"""
    error = context.error
    logger.error(f"Update {update} caused error {error}")
    
    # Детальный лог для отладки
    if hasattr(error, '__traceback__'):
        import traceback
        tb_str = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        logger.error(f"Full traceback:\n{tb_str}")

    if update and update.effective_message:
        # Более информативные сообщения об ошибках
        error_message = "❌ Произошла непредвиденная ошибка."
        
        if "NoneType" in str(error):
            error_message = "❌ Сервис временно недоступен. Попробуйте позже."
        elif "weather" in str(error).lower():
            error_message = "❌ Сервис погоды временно недоступен."
        elif "calculator" in str(error).lower():
            error_message = "❌ Курс валют временно недоступен."
        elif "api" in str(error).lower():
            error_message = "❌ Проблемы с подключением к сервису. Попробуйте позже."
            
        await update.effective_message.reply_text(
            f"{error_message}\n\nПопробуйте еще раз позже."
        )


def main():
    """Основная функция запуска бота"""
    bot_token = os.getenv("BOT_TOKEN")

    if not bot_token:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        return
    
    global PLUGINS_AVAILABLE

    print(f"✅ Токен бота: {bot_token[:20]}...")
    print(f"🔧 DeepSeek API: {'✅ Настроен' if os.getenv('DEEPSEEK_API_KEY') else '❌ Не настроен'}")
    if PLUGINS_AVAILABLE:
        print(f"🌤️ Weather API: {'✅ Настроен' if os.getenv('WEATHER_API_KEY') else '❌ Не настроен'}")
    print("🛡️  ЗАПУСК С УЛЬТРА-ФИЛЬТРАЦИЕЙ")
    print("📊 Анализ файлов: PDF, DOCX, TXT")
    print("🎤 Голосовые сообщения: ВКЛЮЧЕНО")
    if PLUGINS_AVAILABLE:
        print("🔌 Система плагинов: ВКЛЮЧЕНО")
    else:
        print("🔌 Система плагинов: ❌ ОТСУТСТВУЮТ (файлы плагинов не найдены)")
    print("🚫 АКТИВНАЯ цензура ВКЛЮЧЕНА")
    print("🤖 Запуск бота...")

    try:
        application = Application.builder().token(bot_token).build()

         # 1. СНАЧАЛА загружаем плагины (чтобы их обработчики были первыми)
        if PLUGINS_AVAILABLE:
            try:
                # ЯВНО ИМПОРТИРУЕМ ПЛАГИНЫ
                try:
                    from plugins.weather_plugin import WeatherPlugin
                    print("✅ WeatherPlugin imported")
                except ImportError as e:
                    print(f"❌ Failed to import WeatherPlugin: {e}")
                    
                try:
                    from plugins.currency_plugin import CurrencyPlugin
                    print("✅ CurrencyPlugin imported")
                except ImportError as e:
                    print(f"❌ Failed to import CurrencyPlugin: {e}")
                
                plugin_manager.setup_plugins(application)
                print("✅ Плагины успешно загружены")
                
            except Exception as e:
                print(f"❌ Ошибка при загрузке плагинов: {e}")
                PLUGINS_AVAILABLE = False

        # 2. ПОТОМ основные обработчики команд
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("reset", reset_command))

        # 3. Обработчики файлов и изображений
        application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

        # 4. Обработчик голосовых сообщений
        application.add_handler(MessageHandler(filters.VOICE, handle_voice))

        # 5. ОБЩИЙ обработчик текстовых сообщений ДОЛЖЕН БЫТЬ ПОСЛЕДНИМ
        # Он будет обрабатывать только те сообщения, которые не были обработаны плагинами
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        ))

        # Обработчик ошибок
        application.add_error_handler(error_handler)

        # Запуск бота
        logger.info("Bot with ULTRA filtering is starting...")
        print("✅ Бот успешно запущен!")
        print("🛡️  УЛЬТРА-фильтрация АКТИВИРОВАНА")
        print("🎤 Голосовые сообщения: РАБОТАЕТ")
        if PLUGINS_AVAILABLE:
            print("🔌 Плагины: ЗАГРУЖЕНЫ")
        else:
            print("🔌 Плагины: ❌ ОТСУТСТВУЮТ")
        print("🚫 Все нарушения будут блокироваться")
        print("⏹️  Для остановки нажмите Ctrl+C")

        application.run_polling()

    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
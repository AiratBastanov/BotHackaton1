import aiohttp
import os
import json
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from plugins.plugin_base import BasePlugin
from plugins.init import plugin_manager
import logging

logger = logging.getLogger(__name__)


@plugin_manager.register_plugin(
    name="weather",
    description="Плагин для получения прогноза погоды",
    version="1.0"
)
class WeatherPlugin(BasePlugin):
    def __init__(self):
        super().__init__("weather", "Плагин для получения прогноза погоды", "1.0")
        self.api_key = os.getenv("WEATHER_API_KEY")
        self.base_url = "http://api.openweathermap.org/data/2.5"
        
        if not self.api_key or self.api_key == "your_weather_api_key_here":
            logger.warning("❌ Weather API key not configured. Using mock data.")
            self.use_mock_data = True
        else:
            logger.info("✅ Weather API key configured")
            self.use_mock_data = False

    def initialize(self):
        """Инициализация плагина погоды"""
        try:
            if not self.api_key or self.api_key == "your_weather_api_key_here":
                logger.warning("❌ Weather API key not configured. Using mock data.")
                self.use_mock_data = True
            else:
                logger.info("✅ Weather API key configured")
                self.use_mock_data = False
            
            self.initialized = True
            logger.info(f"✅ Weather plugin initialized v{self.version}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize weather plugin: {e}")
            raise
    
    def setup_handlers(self, application):
        """Настройка обработчиков для плагина погоды"""
        # Обработчик команды /weather
        application.add_handler(CommandHandler("weather", self.weather_command))
        
        # Обработчик кнопок погоды
        application.add_handler(MessageHandler(
            filters.Regex(r'^(🌤️ Погода|📍 Ввести другой город|🔄 Выбрать другой город|🌡️ Сейчас|📅 Сегодня|📆 Завтра|📊 На 5 дней)$'),
            self.handle_weather_messages
        ))
        
        # Обработчик выбора города из кнопок
        application.add_handler(MessageHandler(
            filters.Regex(r'^(🏙️ .+|📍 .+)$'),
            self.handle_city_selection
        ))
        
        # Обработчик кнопки "Назад" в контексте погоды
        application.add_handler(MessageHandler(
            filters.Regex(r'^◀️ Назад$'),
            self.handle_back_button
        ))

    async def weather_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /weather"""
        await self._show_city_selection(update)

    async def handle_weather_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений для плагина погоды"""
        user_id = update.effective_user.id
        user_message = update.message.text

        logger.info(f"🌤️ Weather plugin handling message: {user_message} from user {user_id}")

        if user_message == "🌤️ Погода":
            await self._show_city_selection(update)
            return

        if user_message == "📍 Ввести другой город" or user_message == "🔄 Выбрать другой город":
            user_data = self.get_user_data(user_id)
            user_data['awaiting_city_input'] = True
            self.set_user_data(user_id, user_data)
            
            await update.message.reply_text(
                "🏙️ Введите название города:\n\n"
                "Пример: *Лондон*, *Париж*, *Токио*",
                parse_mode='Markdown'
            )
            return

        # Обработка выбора типа прогноза
        if user_message in ["🌡️ Сейчас", "📅 Сегодня", "📆 Завтра", "📊 На 5 дней"]:
            await self._process_forecast_request(update, user_message, user_id)
            return

    async def handle_city_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выбора города из кнопок"""
        user_id = update.effective_user.id
        city_input = update.message.text

        if city_input.startswith("🏙️ "):
            city = city_input[3:]
        elif city_input.startswith("📍 "):
            city = city_input[2:].replace(" (мой город)", "")
        else:
            city = city_input
        
        # Сохраняем город для пользователя
        user_data = self.get_user_data(user_id)
        user_data['city'] = city
        user_data['awaiting_city_input'] = False
        self.set_user_data(user_id, user_data)
        
        # Показываем варианты прогноза
        keyboard = [
            [KeyboardButton("🌡️ Сейчас"), KeyboardButton("📅 Сегодня")],
            [KeyboardButton("📆 Завтра"), KeyboardButton("📊 На 5 дней")],
            [KeyboardButton("🔄 Выбрать другой город"), KeyboardButton("◀️ Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"🏙️ Выбран город: {city}\n\n"
            "Выберите тип прогноза:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def handle_back_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки Назад для плагина погоды"""
        logger.info("Weather plugin handling back button")
        await self._show_main_menu(update)

    async def _show_city_selection(self, update: Update):
        """Показать выбор города"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        saved_city = user_data.get('city')
        
        # Сбрасываем флаг ожидания ввода при показе меню
        user_data['awaiting_city_input'] = False
        self.set_user_data(user_id, user_data)
        
        keyboard = [
            [KeyboardButton("🏙️ Москва"), KeyboardButton("🏙️ Санкт-Петербург")],
            [KeyboardButton("🏙️ Казань"), KeyboardButton("🏙️ Сочи")],
            [KeyboardButton("🏙️ Новосибирск"), KeyboardButton("🏙️ Екатеринбург")],
            [KeyboardButton("📍 Ввести другой город")],
            [KeyboardButton("◀️ Назад")]
        ]
        
        if saved_city:
            keyboard.insert(0, [KeyboardButton(f"📍 {saved_city} (мой город)")])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        message_text = "🌤️ Прогноз погоды\n\n"
        if saved_city:
            message_text += f"Ваш сохраненный город: {saved_city}\n\n"
        
        message_text += "Выберите город из списка или введите название:"
        
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _process_city_input(self, update: Update, city: str, user_id: int):
        """Обработка ввода города текстом"""
        logger.info(f"Processing city input: {city} for user {user_id}")
        
        # Сохраняем город для пользователя и сбрасываем флаг ожидания
        user_data = self.get_user_data(user_id)
        user_data['city'] = city
        user_data['awaiting_city_input'] = False
        self.set_user_data(user_id, user_data)
        
        # Показываем варианты прогноза
        keyboard = [
            [KeyboardButton("🌡️ Сейчас"), KeyboardButton("📅 Сегодня")],
            [KeyboardButton("📆 Завтра"), KeyboardButton("📊 На 5 дней")],
            [KeyboardButton("🔄 Выбрать другой город"), KeyboardButton("◀️ Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"🏙️ Выбран город: {city}\n\n"
            "Выберите тип прогноза:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _process_forecast_request(self, update: Update, forecast_type: str, user_id: int):
        """Обработка запроса прогноза"""
        user_data = self.get_user_data(user_id)
        city = user_data.get('city')
        
        if not city:
            await update.message.reply_text(
                "❌ Сначала выберите город.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🌤️ Погода")]], resize_keyboard=True)
            )
            return

        await update.message.reply_text(f"🌤️ Получаю прогноз для {city}...")

        try:
            if forecast_type == "🌡️ Сейчас":
                weather_data = await self._get_current_weather(city)
                response = self._format_current_weather(weather_data, city)
            elif forecast_type == "📅 Сегодня":
                weather_data = await self._get_forecast(city)
                response = self._format_today_forecast(weather_data, city)
            elif forecast_type == "📆 Завтра":
                weather_data = await self._get_forecast(city)
                response = self._format_tomorrow_forecast(weather_data, city)
            elif forecast_type == "📊 На 5 дней":
                weather_data = await self._get_forecast(city)
                response = self._format_5days_forecast(weather_data, city)
            else:
                response = "❌ Неизвестный тип прогноза"

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Weather API error: {e}")
            await update.message.reply_text(
                "❌ Не удалось получить данные о погоде. "
                "Проверьте название города или попробуйте позже."
            )
    async def _process_city_selection(self, update: Update, city_input: str, user_id: int):
        """Обработка выбора города из кнопки"""
        if city_input.startswith("🏙️ "):
            city = city_input[3:]
        elif city_input.startswith("📍 "):
            city = city_input[2:].replace(" (мой город)", "")
        else:
            city = city_input
        
        # Сохраняем город для пользователя и сбрасываем флаг ожидания
        user_data = self.get_user_data(user_id)
        user_data['city'] = city
        user_data['awaiting_city_input'] = False  # Сбрасываем флаг
        self.set_user_data(user_id, user_data)
        
        # Показываем варианты прогноза
        keyboard = [
            [KeyboardButton("🌡️ Сейчас"), KeyboardButton("📅 Сегодня")],
            [KeyboardButton("📆 Завтра"), KeyboardButton("📊 На 5 дней")],
            [KeyboardButton("🔄 Выбрать другой город"), KeyboardButton("◀️ Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"🏙️ Выбран город: {city}\n\n"
            "Выберите тип прогноза:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _get_current_weather(self, city: str):
        """Получить текущую погоду"""
        logger.info(f"Getting current weather for: {city}")
        
        if self.use_mock_data:
            logger.info("Using mock weather data")
            return self._get_mock_weather_data(city)
        
        url = f"{self.base_url}/weather"
        params = {
            'q': city,
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'ru'
        }
        
        logger.info(f"Making API request to: {url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    logger.info(f"Weather API response status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Weather API success for {city}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Weather API error: {response.status} - {error_text}")
                        # При ошибке API используем мок-данные
                        return self._get_mock_weather_data(city)
        except Exception as e:
            logger.error(f"Weather API request failed: {e}")
            # При ошибке сети используем мок-данные
            return self._get_mock_weather_data(city)

    async def _get_forecast(self, city: str):
        """Получить прогноз погоды"""
        logger.info(f"Getting forecast for: {city}")
        
        if self.use_mock_data:
            logger.info("Using mock forecast data")
            return self._get_mock_forecast_data(city)
        
        url = f"{self.base_url}/forecast"
        params = {
            'q': city,
            'appid': self.api_key,
            'units': 'metric',
            'lang': 'ru'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Weather API error: {response.status} - {error_text}")
                        # При ошибке API используем мок-данные
                        return self._get_mock_forecast_data(city)
        except Exception as e:
            logger.error(f"Weather API request failed: {e}")
            # При ошибке сети используем мок-данные
            return self._get_mock_forecast_data(city)

    def _get_mock_weather_data(self, city: str):
        """Мок-данные для демонстрации (только если API ключ не настроен)"""
        import random
        current_time = datetime.now()
        
        # Сезонные температуры
        month = current_time.month
        if month in [12, 1, 2]:  # Зима
            base_temp = random.randint(-15, 0)
        elif month in [3, 4, 5]:  # Весна
            base_temp = random.randint(5, 18)
        elif month in [6, 7, 8]:  # Лето
            base_temp = random.randint(18, 30)
        else:  # Осень
            base_temp = random.randint(5, 15)
        
        weather_types = [
            {"main": "Clear", "description": "ясно"},
            {"main": "Clouds", "description": "облачно"},
            {"main": "Rain", "description": "дождь"},
            {"main": "Snow", "description": "снег"}
        ]
        weather = random.choice(weather_types)
        
        return {
            'name': city,
            'main': {
                'temp': base_temp,
                'feels_like': base_temp - random.randint(1, 3),
                'humidity': random.randint(40, 90),
                'pressure': random.randint(980, 1030)
            },
            'weather': [weather],
            'wind': {'speed': random.randint(1, 10)}
        }

    def _get_mock_forecast_data(self, city: str):
        """Мок-данные прогноза"""
        forecasts = []
        for i in range(40):  # 5 дней * 8 прогнозов
            forecast_time = datetime.now() + timedelta(hours=i*3)
            temp = 15 + i % 10 - 5  # Колебания температуры
            
            forecasts.append({
                'dt_txt': forecast_time.strftime('%Y-%m-%d %H:%M:%S'),
                'main': {
                    'temp': temp,
                    'feels_like': temp - 2,
                    'humidity': 60 + i % 30
                },
                'weather': [{
                    'description': ['ясно', 'облачно', 'дождь', 'снег'][i % 4],
                    'main': ['Clear', 'Clouds', 'Rain', 'Snow'][i % 4]
                }],
                'wind': {'speed': 2 + i % 6}
            })
        
        return {
            'city': {'name': city},
            'list': forecasts
        }

    def _format_current_weather(self, data, city: str) -> str:
        """Форматирование текущей погоды"""
        main = data['main']
        weather = data['weather'][0]
        
        weather_emojis = {
            'ясно': '☀️',
            'облачно': '⛅',
            'дождь': '🌧️',
            'снег': '❄️',
            'туман': '🌫️'
        }
        
        emoji = weather_emojis.get(weather['description'], '🌤️')
        
        return (
            f"{emoji} Погода в {city}\n\n"
            f"{weather['description'].title()}\n"
            f"🌡️ Температура: {main['temp']:.1f}°C\n"
            f"💨 Ощущается как: {main['feels_like']:.1f}°C\n"
            f"💧 Влажность: {main['humidity']}%\n"
            f"🌬️ Давление: {main['pressure']} hPa\n"
            f"💨 Ветер: {data['wind']['speed']} м/с\n\n"
            f"🕐 *Обновлено: {datetime.now().strftime('%H:%M')}*"
        )

    def _format_today_forecast(self, data, city: str) -> str:
        """Форматирование прогноза на сегодня"""
        today = datetime.now().strftime('%Y-%m-%d')
        today_forecasts = [item for item in data['list'] if item['dt_txt'].startswith(today)]
        
        if not today_forecasts:
            return f"❌ Нет данных на сегодня для {city}"
        
        result = f"📅 Прогноз на сегодня для {city}\n\n"
        
        for forecast in today_forecasts[:4]:  # Первые 4 прогноза
            time_str = datetime.strptime(forecast['dt_txt'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
            temp = forecast['main']['temp']
            desc = forecast['weather'][0]['description']
            
            result += f"🕐 {time_str}: {desc}, {temp:.1f}°C\n"
        
        return result

    def _format_tomorrow_forecast(self, data, city: str) -> str:
        """Форматирование прогноза на завтра"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        tomorrow_forecasts = [item for item in data['list'] if item['dt_txt'].startswith(tomorrow)]
        
        if not tomorrow_forecasts:
            return f"❌ Нет данных на завтра для {city}"
        
        # Берем дневной прогноз (около 12:00)
        day_forecast = tomorrow_forecasts[len(tomorrow_forecasts)//2] if len(tomorrow_forecasts) > 2 else tomorrow_forecasts[0]
        
        main = day_forecast['main']
        weather = day_forecast['weather'][0]
        
        return (
            f"📆 Прогноз на завтра для {city}\n\n"
            f"{weather['description'].title()}\n"
            f"🌡️ Температура: {main['temp']:.1f}°C\n"
            f"💧 Влажность: {main['humidity']}%\n"
            f"💨 Ветер: {day_forecast['wind']['speed']} м/с"
        )

    def _format_5days_forecast(self, data, city: str) -> str:
        """Форматирование прогноза на 5 дней"""
        forecasts_by_day = {}
        
        for item in data['list']:
            date = item['dt_txt'].split()[0]
            if date not in forecasts_by_day:
                forecasts_by_day[date] = []
            forecasts_by_day[date].append(item)
        
        # Берем следующие 5 дней (исключая сегодня)
        next_5_days = sorted(forecasts_by_day.keys())[1:6]
        
        result = f"📊 Прогноз на 5 дней для {city}\n\n"
        
        for date in next_5_days:
            day_forecasts = forecasts_by_day[date]
            # Берем дневной прогноз
            day_forecast = day_forecasts[len(day_forecasts)//2]
            
            main = day_forecast['main']
            weather = day_forecast['weather'][0]
            
            # Форматируем дату
            forecast_date = datetime.strptime(date, '%Y-%m-%d')
            date_str = forecast_date.strftime('%d.%m')
            day_name = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][forecast_date.weekday()]
            
            weather_emojis = {
                'ясно': '☀️',
                'облачно': '⛅',
                'дождь': '🌧️',
                'снег': '❄️'
            }
            emoji = weather_emojis.get(weather['description'], '🌤️')
            
            result += f"{emoji} {day_name} {date_str}: {weather['description']}, {main['temp']:.0f}°C\n"
        
        result += f"\n💡 *Обновлено: {datetime.now().strftime('%H:%M')}*"
        return result

    async def _show_main_menu(self, update: Update):
        """Показать главное меню"""
        keyboard = [
            [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
            [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
            [KeyboardButton("📊 Анализ файлов"), KeyboardButton("🌤️ Погода"), KeyboardButton("💱 Курсы валют")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=reply_markup)
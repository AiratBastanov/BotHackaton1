import aiohttp
import os
import json
import re
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler
from plugins.plugin_base import BasePlugin
from plugins.init import plugin_manager
import logging

logger = logging.getLogger(__name__)


@plugin_manager.register_plugin(
    name="currency",
    description="Курсы валют и конвертер",
    version="1.3"
)
class CurrencyPlugin(BasePlugin):
    def __init__(self):
        super().__init__("currency", "Курсы валют и конвертер", "1.3")
        self.cbr_url = "https://www.cbr-xml-daily.ru/daily_json.js"
        self.cache = {}
        self.cache_timeout = 300  # 5 минут
        self.supported_currencies = {
            'USD': 'Доллар США', 'EUR': 'Евро', 'GBP': 'Фунт стерлингов',
            'CNY': 'Китайский юань', 'JPY': 'Японская иена', 'CHF': 'Швейцарский франк',
            'TRY': 'Турецкая лира', 'KZT': 'Казахстанский тенге', 'RUB': 'Российский рубль'
        }

    def initialize(self):
        """Инициализация плагина валют"""
        try:
            self.initialized = True
            logger.info(f"✅ Currency plugin initialized v{self.version}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize currency plugin: {e}")
            raise
    
    def setup_handlers(self, application):
        """Настройка обработчиков для плагина валют"""
        # Обработчик команды /currency
        application.add_handler(CommandHandler("currency", self.currency_command))
        
        # Обработчик кнопок валют
        application.add_handler(MessageHandler(
            filters.Regex(r'^(💱 Курсы валют|💵 Основные валюты|🔄 Конвертер|📊 Все курсы|📈 Изменения)$'),
            self.handle_currency_messages
        ))
        
        # Обработчик кнопки "Назад" в контексте валют
        application.add_handler(MessageHandler(
            filters.Regex(r'^◀️ Назад$'),
            self.handle_back_button
        ))
        
        # Обработчик текстовых запросов для конвертера (добавьте этот обработчик)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text_conversion
        ), group=1)  # Указываем группу, чтобы этот обработчик работал параллельно
        
        logger.info("✅ Currency plugin handlers setup completed")

    async def handle_text_conversion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых запросов для конвертации валют"""
        user_message = update.message.text.strip()
        
        # Пропускаем сообщения, которые уже обработаны другими плагинами
        if user_message in ["💱 Курсы валют", "💵 Основные валюты", "🔄 Конвертер", 
                           "📊 Все курсы", "📈 Изменения", "◀️ Назад"]:
            return
        
        # Проверяем, является ли сообщение запросом на конвертацию
        conversion_data = self._parse_conversion_request(user_message)
        if conversion_data:
            await self._process_conversion(update, conversion_data)
            return True  # Сообщение обработано
        
        return False  # Сообщение не обработано

    def _parse_conversion_request(self, text: str) -> dict:
        """Парсит текстовый запрос на конвертацию валют"""
        # Паттерны для распознавания запросов
        patterns = [
            r'(\d+(?:[.,]\d+)?)\s*([a-zA-Zа-яА-Я]{3,})\s+(?:в|to|->)\s+([a-zA-Zа-яА-Я]{3,})',
            r'конвертировать\s+(\d+(?:[.,]\d+)?)\s+([a-zA-Zа-яА-Я]{3,})\s+(?:в|в)\s+([a-zA-Zа-яА-Я]{3,})',
            r'перевести\s+(\d+(?:[.,]\d+)?)\s+([a-zA-Zа-яА-Я]{3,})\s+(?:в|в)\s+([a-zA-Zа-яА-Я]{3,})',
            r'(\d+(?:[.,]\d+)?)\s*\$?\s*(?:доллар|usd)\s*(?:в|to)\s*(?:рубл|rub)',
            r'(\d+(?:[.,]\d+)?)\s*(?:евро|eur)\s*(?:в|to)\s*(?:рубл|rub)',
            r'(\d+(?:[.,]\d+)?)\s*(?:рубл|rub)\s*(?:в|to)\s*(?:доллар|\$|usd)',
            r'(\d+(?:[.,]\d+)?)\s*(?:рубл|rub)\s*(?:в|to)\s*(?:евро|eur)'
        ]
        
        text_lower = text.lower()
        
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(',', '.'))
                
                if len(match.groups()) == 3:
                    from_currency = self._normalize_currency(match.group(2))
                    to_currency = self._normalize_currency(match.group(3))
                else:
                    # Для специальных паттернов с 1 группой
                    if 'доллар' in text_lower or 'usd' in text_lower or '$' in text:
                        if 'рубл' in text_lower:
                            from_currency = 'USD'
                            to_currency = 'RUB'
                        else:
                            from_currency = 'RUB'
                            to_currency = 'USD'
                    elif 'евро' in text_lower or 'eur' in text_lower:
                        if 'рубл' in text_lower:
                            from_currency = 'EUR'
                            to_currency = 'RUB'
                        else:
                            from_currency = 'RUB'
                            to_currency = 'EUR'
                
                if from_currency and to_currency:
                    return {
                        'amount': amount,
                        'from_currency': from_currency,
                        'to_currency': to_currency,
                        'original_text': text
                    }
        
        return None

    def _normalize_currency(self, currency_str: str) -> str:
        """Нормализует название валюты к стандартному коду"""
        currency_map = {
            # Русские названия
            'рубль': 'RUB', 'руб': 'RUB', 'рублей': 'RUB', 'р': 'RUB',
            'доллар': 'USD', 'долларов': 'USD', 'доллары': 'USD', 'usd': 'USD', '$': 'USD',
            'евро': 'EUR', 'eur': 'EUR', '€': 'EUR',
            'юань': 'CNY', 'юаней': 'CNY', 'cny': 'CNY',
            'фунт': 'GBP', 'фунтов': 'GBP', 'gbp': 'GBP',
            'иена': 'JPY', 'иен': 'JPY', 'yen': 'JPY', 'jpy': 'JPY',
            'франк': 'CHF', 'франков': 'CHF', 'chf': 'CHF',
            'лира': 'TRY', 'лир': 'TRY', 'try': 'TRY',
            'тенге': 'KZT', 'kzt': 'KZT',
            
            # Английские названия
            'ruble': 'RUB', 'rubl': 'RUB',
            'dollar': 'USD',
            'euro': 'EUR',
            'yuan': 'CNY',
            'pound': 'GBP',
            'yen': 'JPY',
            'frank': 'CHF',
            'lira': 'TRY',
            'tenge': 'KZT'
        }
        
        # Проверяем напрямую
        clean_str = currency_str.strip().lower()
        if clean_str in currency_map:
            return currency_map[clean_str]
        
        # Проверяем по коду (если введен код валюты)
        if clean_str.upper() in self.supported_currencies:
            return clean_str.upper()
        
        return None

    async def _process_conversion(self, update: Update, conversion_data: dict):
        """Обрабатывает конвертацию валют"""
        amount = conversion_data['amount']
        from_curr = conversion_data['from_currency']
        to_curr = conversion_data['to_currency']
        
        await update.message.reply_text(f"💱 Конвертирую {amount} {from_curr} в {to_curr}...")
        
        try:
            rates_data = await self._get_cbr_rates()
            
            if from_curr not in rates_data or to_curr not in rates_data:
                await update.message.reply_text(
                    f"❌ Не удалось найти курсы для указанных валют.\n"
                    f"Доступные валюты: {', '.join(self.supported_currencies.keys())}"
                )
                return
            
            # Конвертация через RUB как базовую валюту
            if from_curr == 'RUB':
                from_rate = 1.0
            else:
                from_rate = rates_data[from_curr]['value']
            
            if to_curr == 'RUB':
                to_rate = 1.0
            else:
                to_rate = rates_data[to_curr]['value']
            
            # Конвертируем
            if from_curr == 'RUB':
                result = amount / to_rate
            elif to_curr == 'RUB':
                result = amount * from_rate
            else:
                # Конвертация между двумя валютами через RUB
                result = (amount * from_rate) / to_rate
            
            # Форматируем результат
            from_currency_name = self.supported_currencies.get(from_curr, from_curr)
            to_currency_name = self.supported_currencies.get(to_curr, to_curr)
            
            response = (
                f"💱 *Результат конвертации:*\n\n"
                f"💰 *{amount:.2f} {from_curr}* ({from_currency_name}) = "
                f"*{result:.2f} {to_curr}* ({to_currency_name})\n\n"
            )
            
            # Добавляем курсы
            if from_curr != 'RUB':
                response += f"📊 Курс {from_curr}: {rates_data[from_curr]['value']:.2f} RUB\n"
            if to_curr != 'RUB':
                response += f"📊 Курс {to_curr}: {rates_data[to_curr]['value']:.2f} RUB\n"
            
            response += f"\n🕐 *Курсы ЦБ РФ на {rates_data.get('date', 'сегодня')}*"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await update.message.reply_text(
                "❌ Ошибка при конвертации. Попробуйте позже."
            )

    # Остальные методы класса остаются без изменений...
    async def currency_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /currency"""
        logger.info("Currency command called")
        await self._show_main_menu(update)

    async def handle_currency_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений для плагина валют"""
        user_message = update.message.text
        logger.info(f"🔄 Currency plugin handling message: {user_message}")

        if user_message == "💱 Курсы валют":
            await self._show_main_menu(update)
            return

        if user_message == "💵 Основные валюты":
            await self._show_fiat_rates(update)
            return

        if user_message == "🔄 Конвертер":
            await update.message.reply_text(
                "💱 Конвертер валют\n\n"
                "Введите запрос в формате:\n"
                "`100 USD to RUB`\n"
                "`1000 RUB to EUR`\n"
                "`500 долларов в рубли`\n"
                "`конвертировать 50 евро в доллары`\n\n"
                "Или выберите из меню выше ⬆️",
                parse_mode='Markdown'
            )
            return

        if user_message == "📊 Все курсы":
            await self._show_all_rates(update)
            return

        if user_message == "📈 Изменения":
            await self._show_changes(update)
            return

    async def handle_back_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки Назад для плагина валют"""
        logger.info("Currency plugin handling back button")
        await self._show_main_menu_back(update)

    async def _show_main_menu(self, update: Update):
        """Показать главное меню валют"""
        logger.info("Showing currency main menu")
        keyboard = [
            [KeyboardButton("💵 Основные валюты"), KeyboardButton("📊 Все курсы")],
            [KeyboardButton("🔄 Конвертер"), KeyboardButton("📈 Изменения")],
            [KeyboardButton("◀️ Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "💱 *Курсы валют и конвертер*\n\n"
            "• 💵 *Основные валюты* - USD, EUR, CNY, GBP\n"
            "• 🔄 *Конвертер* - перевод между валютами\n"
            "• 📊 *Все курсы* - полный список\n"
            "• 📈 *Изменения* - динамика за сутки\n\n"
            "*Примеры запросов:*\n"
            "`100 USD to RUB`\n"
            "`500 евро в доллары`\n"
            "`конвертировать 1000 рублей в юани`\n\n"
            "Выберите опцию:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _show_fiat_rates(self, update: Update):
        """Показать курсы основных валют"""
        logger.info("Showing fiat rates")
        await update.message.reply_text("💵 Получаю курсы валют...")

        try:
            rates_data = await self._get_cbr_rates()
            logger.info(f"Rates data received: {bool(rates_data)}")
            
            if not rates_data:
                await update.message.reply_text("❌ Не удалось получить данные о валютах")
                return

            usd_rate = rates_data.get('USD', {})
            eur_rate = rates_data.get('EUR', {})
            cny_rate = rates_data.get('CNY', {})
            gbp_rate = rates_data.get('GBP', {})

            response = (
                "💵 *Курсы ЦБ РФ на сегодня*\n\n"
                f"🇺🇸 *USD:* {usd_rate.get('value', 'N/A'):.2f} ₽ "
                f"({usd_rate.get('change', 0):+.2f})\n"
                f"🇪🇺 *EUR:* {eur_rate.get('value', 'N/A'):.2f} ₽ "
                f"({eur_rate.get('change', 0):+.2f})\n"
                f"🇨🇳 *CNY:* {cny_rate.get('value', 'N/A'):.2f} ₽ "
                f"({cny_rate.get('change', 0):+.2f})\n"
                f"🇬🇧 *GBP:* {gbp_rate.get('value', 'N/A'):.2f} ₽ "
                f"({gbp_rate.get('change', 0):+.2f})\n\n"
                f"🕐 *Обновлено:* {datetime.now().strftime('%H:%M')}\n"
                f"📅 *Дата:* {rates_data.get('date', 'N/A')}"
            )

            await update.message.reply_text(response, parse_mode='Markdown')
            logger.info("Fiat rates displayed successfully")

        except Exception as e:
            logger.error(f"Fiat rates error: {e}")
            await update.message.reply_text(
                "❌ Ошибка получения курсов валют. Попробуйте позже."
            )

    async def _show_all_rates(self, update: Update):
        """Показать все курсы валют"""
        logger.info("Showing all rates")
        await update.message.reply_text("📊 Получаю все курсы...")

        try:
            rates_data = await self._get_cbr_rates()
            if not rates_data:
                await update.message.reply_text("❌ Не удалось получить данные")
                return

            # Основные валюты
            main_currencies = ['USD', 'EUR', 'CNY', 'GBP', 'JPY', 'CHF', 'TRY', 'KZT']
            
            response = "📊 *Все курсы ЦБ РФ*\n\n"
            
            for currency in main_currencies:
                if currency in rates_data:
                    rate_data = rates_data[currency]
                    response += f"• {self._get_currency_flag(currency)} *{currency}:* {rate_data.get('value', 'N/A'):.2f} ₽\n"

            response += f"\n🕐 *Обновлено:* {datetime.now().strftime('%H:%M')}"
            response += f"\n📅 *Дата:* {rates_data.get('date', 'N/A')}"

            await update.message.reply_text(response, parse_mode='Markdown')
            logger.info("All rates displayed successfully")

        except Exception as e:
            logger.error(f"All rates error: {e}")
            await update.message.reply_text(
                "❌ Ошибка получения курсов. Попробуйте позже."
            )

    async def _show_changes(self, update: Update):
        """Показать изменения курсов"""
        logger.info("Showing currency changes")
        await update.message.reply_text("📈 Анализирую изменения...")

        try:
            rates_data = await self._get_cbr_rates()
            if not rates_data:
                await update.message.reply_text("❌ Не удалось получить данные")
                return

            response = "📈 *Изменения курсов за сутки*\n\n"
            
            for currency in ['USD', 'EUR', 'CNY']:
                if currency in rates_data:
                    rate_data = rates_data[currency]
                    change = rate_data.get('change', 0)
                    change_percent = rate_data.get('change_percent', 0)
                    
                    if change > 0:
                        trend = "📈"
                    elif change < 0:
                        trend = "📉"
                    else:
                        trend = "➡️"
                    
                    response += f"{trend} {self._get_currency_flag(currency)} *{currency}:* {change:+.2f} ₽ ({change_percent:+.1f}%)\n"

            response += f"\n🕐 *Обновлено:* {datetime.now().strftime('%H:%M')}"

            await update.message.reply_text(response, parse_mode='Markdown')
            logger.info("Currency changes displayed successfully")

        except Exception as e:
            logger.error(f"Changes error: {e}")
            await update.message.reply_text(
                "❌ Ошибка анализа изменений. Попробуйте позже."
            )

    async def _get_cbr_rates(self):
        """Получить курсы валют от ЦБ РФ"""
        cache_key = "cbr_rates"
        if cache_key in self.cache:
            cache_time, data = self.cache[cache_key]
            if datetime.now().timestamp() - cache_time < self.cache_timeout:
                logger.info("Using cached currency rates")
                return data

        try:
            logger.info("Fetching fresh currency rates from CBR")
            async with aiohttp.ClientSession() as session:
                async with session.get(self.cbr_url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("Successfully fetched currency rates from CBR")
                        
                        rates = {}
                        for currency, rate_info in data['Valute'].items():
                            rates[currency] = {
                                'value': rate_info['Value'],
                                'previous': rate_info['Previous'],
                                'change': rate_info['Value'] - rate_info['Previous'],
                                'change_percent': ((rate_info['Value'] - rate_info['Previous']) / rate_info['Previous']) * 100
                            }
                        
                        rates['date'] = data['Date'][:10]
                        
                        # Кешируем данные
                        self.cache[cache_key] = (datetime.now().timestamp(), rates)
                        return rates
                    else:
                        logger.error(f"CBR API error: {response.status}")
                        return self._get_mock_rates()
        except Exception as e:
            logger.error(f"CBR API request failed: {e}")
            return self._get_mock_rates()

    def _get_mock_rates(self):
        """Мок-данные для валют (если API недоступно)"""
        logger.info("Using mock currency rates")
        return {
            'USD': {'value': 91.5, 'previous': 90.8, 'change': 0.7, 'change_percent': 0.77},
            'EUR': {'value': 99.2, 'previous': 98.5, 'change': 0.7, 'change_percent': 0.71},
            'CNY': {'value': 12.8, 'previous': 12.7, 'change': 0.1, 'change_percent': 0.79},
            'GBP': {'value': 115.3, 'previous': 114.9, 'change': 0.4, 'change_percent': 0.35},
            'JPY': {'value': 0.61, 'previous': 0.60, 'change': 0.01, 'change_percent': 1.67},
            'CHF': {'value': 105.2, 'previous': 104.8, 'change': 0.4, 'change_percent': 0.38},
            'TRY': {'value': 2.8, 'previous': 2.7, 'change': 0.1, 'change_percent': 3.70},
            'KZT': {'value': 0.19, 'previous': 0.19, 'change': 0.0, 'change_percent': 0.0},
            'date': datetime.now().strftime('%Y-%m-%d')
        }

    def _get_currency_flag(self, currency: str) -> str:
        """Получить флаг валюты"""
        flags = {
            'USD': '🇺🇸',
            'EUR': '🇪🇺', 
            'CNY': '🇨🇳',
            'GBP': '🇬🇧',
            'JPY': '🇯🇵',
            'CHF': '🇨🇭',
            'TRY': '🇹🇷',
            'KZT': '🇰🇿',
            'RUB': '🇷🇺'
        }
        return flags.get(currency, '💱')

    async def _show_main_menu_back(self, update: Update):
        """Вернуться в главное меню бота"""
        logger.info("Returning to main menu from currency")
        keyboard = [
            [KeyboardButton("❓ Помощь"), KeyboardButton("ℹ️ О боте")],
            [KeyboardButton("🔄 Сбросить диалог"), KeyboardButton("💡 Примеры запросов")],
            [KeyboardButton("📊 Анализ файлов"), KeyboardButton("🌤️ Погода"), KeyboardButton("💱 Курсы валют")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=reply_markup)
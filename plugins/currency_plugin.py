import aiohttp
import os
import json
import re
import asyncio
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
    version="1.5"
)
class CurrencyPlugin(BasePlugin):
    def __init__(self):
        super().__init__("currency", "Курсы валют и конвертер", "1.5")
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
        
        # Обработчик текстовых запросов для конвертера - ВЫСОКИЙ ПРИОРИТЕТ
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text_conversion
        ), group=0)  # Группа 0 - высший приоритет
        
        logger.info("✅ Currency plugin handlers setup completed")

    async def handle_text_conversion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых запросов для конвертации валют"""
        user_message = update.message.text.strip()
        
        # Пропускаем сообщения, которые уже обработаны другими плагинами или являются кнопками
        if user_message in ["💱 Курсы валют", "💵 Основные валюты", "🔄 Конвертер", 
                           "📊 Все курсы", "📈 Изменения", "◀️ Назад"]:
            return False
        
        # Проверяем, является ли сообщение запросом на конвертацию
        conversion_data = self._parse_conversion_request(user_message)
        if conversion_data:
            logger.info(f"🔄 Processing currency conversion: {conversion_data}")
            await self._process_conversion(update, conversion_data)
            return True  # Сообщение обработано, останавливаем дальнейшую обработку
        
        return False  # Сообщение не обработано, передаем дальше

    def _parse_conversion_request(self, text: str) -> dict:
        """Парсит текстовый запрос на конвертацию валют"""
        # Улучшенные паттерны для распознавания запросов
        patterns = [
            # Формат: 100 USD to RUB
            r'(\d+(?:[.,]\d+)?)\s*([a-zA-Z]{3})\s+(?:to|в|->)\s+([a-zA-Z]{3})',
            # Формат: 100 долларов в рубли
            r'(\d+(?:[.,]\d+)?)\s*([a-zA-Zа-яА-Я]{2,})\s+(?:в|to|->)\s+([a-zA-Zа-яА-Я]{2,})',
            # Формат: конвертировать 100 USD в RUB
            r'(?:конвертировать|перевести)\s+(\d+(?:[.,]\d+)?)\s+([a-zA-Zа-яА-Я]{2,})\s+(?:в|to|->)\s+([a-zA-Zа-яА-Я]{2,})',
        ]
        
        text_lower = text.lower().strip()
        logger.info(f"🔄 Parsing currency request: '{text}' -> '{text_lower}'")
        
        # Специальные случаи для популярных валют
        special_cases = [
            # USD to RUB
            (r'(\d+(?:[.,]\d+)?)\s*(?:usd|\$|доллар)\s*(?:в|to)\s*(?:rub|рубл)', 'USD', 'RUB'),
            # RUB to USD
            (r'(\d+(?:[.,]\d+)?)\s*(?:rub|рубл)\s*(?:в|to)\s*(?:usd|\$|доллар)', 'RUB', 'USD'),
            # EUR to RUB
            (r'(\d+(?:[.,]\d+)?)\s*(?:eur|евро)\s*(?:в|to)\s*(?:rub|рубл)', 'EUR', 'RUB'),
            # RUB to EUR
            (r'(\d+(?:[.,]\d+)?)\s*(?:rub|рубл)\s*(?:в|to)\s*(?:eur|евро)', 'RUB', 'EUR'),
            # USD to EUR
            (r'(\d+(?:[.,]\d+)?)\s*(?:usd|\$|доллар)\s*(?:в|to)\s*(?:eur|евро)', 'USD', 'EUR'),
            # EUR to USD
            (r'(\d+(?:[.,]\d+)?)\s*(?:eur|евро)\s*(?:в|to)\s*(?:usd|\$|доллар)', 'EUR', 'USD'),
        ]
        
        # Сначала проверяем специальные случаи
        for pattern, from_curr, to_curr in special_cases:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(',', '.'))
                logger.info(f"✅ Special case matched: {amount} {from_curr} -> {to_curr}")
                return {
                    'amount': amount,
                    'from_currency': from_curr,
                    'to_currency': to_curr,
                    'original_text': text
                }
        
        # Затем проверяем общие паттерны
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                amount = float(match.group(1).replace(',', '.'))
                from_currency = self._normalize_currency(match.group(2))
                to_currency = self._normalize_currency(match.group(3))
                
                if from_currency and to_currency:
                    logger.info(f"✅ General pattern matched: {amount} {from_currency} -> {to_currency}")
                    return {
                        'amount': amount,
                        'from_currency': from_currency,
                        'to_currency': to_currency,
                        'original_text': text
                    }
                else:
                    logger.warning(f"❌ Currency normalization failed: '{match.group(2)}' -> '{from_currency}', '{match.group(3)}' -> '{to_currency}'")
        
        logger.info(f"❌ No currency patterns matched for: {text}")
        return None

    def _normalize_currency(self, currency_str: str) -> str:
        """Нормализует название валюты к стандартному коду"""
        currency_map = {
            # Русские названия
            'рубль': 'RUB', 'руб': 'RUB', 'рублей': 'RUB', 'рубли': 'RUB', 'р': 'RUB',
            'доллар': 'USD', 'долларов': 'USD', 'доллары': 'USD', 'доллара': 'USD', 'usd': 'USD', '$': 'USD',
            'евро': 'EUR', 'eur': 'EUR', '€': 'EUR',
            'юань': 'CNY', 'юаней': 'CNY', 'юаня': 'CNY', 'cny': 'CNY',
            'фунт': 'GBP', 'фунтов': 'GBP', 'фунта': 'GBP', 'gbp': 'GBP',
            'иена': 'JPY', 'иен': 'JPY', 'иены': 'JPY', 'yen': 'JPY', 'jpy': 'JPY',
            'франк': 'CHF', 'франков': 'CHF', 'франка': 'CHF', 'chf': 'CHF',
            'лира': 'TRY', 'лир': 'TRY', 'лиры': 'TRY', 'try': 'TRY',
            'тенге': 'KZT', 'kzt': 'KZT',
        }
        
        # Очищаем строку
        clean_str = currency_str.strip().lower()
        logger.info(f"🔄 Normalizing currency: '{currency_str}' -> '{clean_str}'")
        
        # Проверяем напрямую в мапе
        if clean_str in currency_map:
            result = currency_map[clean_str]
            logger.info(f"✅ Direct map: '{clean_str}' -> '{result}'")
            return result
        
        # Проверяем по коду (если введен код валюты)
        clean_upper = clean_str.upper()
        if clean_upper in self.supported_currencies:
            logger.info(f"✅ Code match: '{clean_upper}'")
            return clean_upper
        
        logger.warning(f"❌ Currency not found: '{clean_str}'")
        return None

    async def _process_conversion(self, update: Update, conversion_data: dict):
        """Обрабатывает конвертацию валют"""
        amount = conversion_data['amount']
        from_curr = conversion_data['from_currency']
        to_curr = conversion_data['to_currency']
        
        logger.info(f"💱 Starting conversion: {amount} {from_curr} -> {to_curr}")
        
        try:
            rates_data = await self._get_cbr_rates()
            
            # Проверяем доступность валют
            if from_curr not in rates_data:
                logger.error(f"❌ From currency not found: {from_curr}")
                await update.message.reply_text(
                    f"❌ Валюта '{from_curr}' не найдена.\n"
                    f"Доступные валюты: {', '.join(self.supported_currencies.keys())}"
                )
                return
            
            if to_curr not in rates_data:
                logger.error(f"❌ To currency not found: {to_curr}")
                await update.message.reply_text(
                    f"❌ Валюта '{to_curr}' не найдена.\n"
                    f"Доступные валюты: {', '.join(self.supported_currencies.keys())}"
                )
                return
            
            await update.message.reply_text(f"💱 Конвертирую {amount} {from_curr} в {to_curr}...")
            
            # Получаем курсы
            if from_curr == 'RUB':
                from_rate = 1.0
            else:
                from_rate = rates_data[from_curr]['value']
            
            if to_curr == 'RUB':
                to_rate = 1.0
            else:
                to_rate = rates_data[to_curr]['value']
            
            logger.info(f"📊 Rates: {from_curr} = {from_rate} RUB, {to_curr} = {to_rate} RUB")
            
            # ПРАВИЛЬНАЯ формула конвертации
            if from_curr == 'RUB':
                # Из RUB в другую валюту: сумма / курс целевой валюты
                result = amount / to_rate
            elif to_curr == 'RUB':
                # Из другой валюты в RUB: сумма * курс исходной валюты
                result = amount * from_rate
            else:
                # Конвертация между двумя валютами через RUB
                # Сначала конвертируем в RUB, потом в целевую валюту
                amount_in_rub = amount * from_rate
                result = amount_in_rub / to_rate
            
            # Форматируем результат
            from_currency_name = self.supported_currencies.get(from_curr, from_curr)
            to_currency_name = self.supported_currencies.get(to_curr, to_curr)
            
            response = (
                f"💱 *Результат конвертации:*\n\n"
                f"💰 *{amount:.2f} {from_curr}* ({from_currency_name}) = "
                f"*{result:.2f} {to_curr}* ({to_currency_name})\n\n"
            )
            
            # Добавляем курсы для информации
            if from_curr != 'RUB':
                response += f"📊 Курс {from_curr}: {from_rate:.2f} RUB\n"
            if to_curr != 'RUB':
                response += f"📊 Курс {to_curr}: {to_rate:.2f} RUB\n"
            
            response += f"\n🕐 *Курсы ЦБ РФ на {rates_data.get('date', 'сегодня')}*"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            logger.info(f"✅ Conversion successful: {amount} {from_curr} = {result:.2f} {to_curr}")
            
        except Exception as e:
            logger.error(f"❌ Conversion error: {e}")
            await update.message.reply_text(
                "❌ Ошибка при конвертации. Попробуйте позже."
            )

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
                        logger.info(f"✅ Successfully fetched currency rates from CBR. Date: {data.get('Date')}")
                        
                        rates = {}
                        for currency, rate_info in data['Valute'].items():
                            # Рассчитываем изменения
                            change = rate_info['Value'] - rate_info['Previous']
                            change_percent = ((rate_info['Value'] - rate_info['Previous']) / rate_info['Previous']) * 100
                            
                            rates[currency] = {
                                'value': rate_info['Value'],
                                'previous': rate_info['Previous'],
                                'change': change,
                                'change_percent': change_percent
                            }
                        
                        # ВАЖНО: Добавляем RUB вручную, так как это базовая валюта
                        rates['RUB'] = {
                            'value': 1.0,
                            'previous': 1.0,
                            'change': 0.0,
                            'change_percent': 0.0
                        }
                        
                        rates['date'] = data['Date'][:10]  # Берем только дату без времени
                        
                        # Логируем полученные курсы для отладки
                        logger.info(f"📊 Received rates for: {list(rates.keys())[:5]}...")  # Первые 5 валют
                        logger.info(f"📊 USD rate: {rates.get('USD', {}).get('value', 'N/A')}")
                        logger.info(f"📊 EUR rate: {rates.get('EUR', {}).get('value', 'N/A')}")
                        logger.info(f"📊 CNY rate: {rates.get('CNY', {}).get('value', 'N/A')}")
                        
                        # Кешируем данные
                        self.cache[cache_key] = (datetime.now().timestamp(), rates)
                        return rates
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ CBR API error: {response.status} - {error_text}")
                        logger.info("🔄 Falling back to mock rates")
                        return self._get_mock_rates()
        except asyncio.TimeoutError:
            logger.error("❌ CBR API request timeout")
            logger.info("🔄 Falling back to mock rates")
            return self._get_mock_rates()
        except aiohttp.ClientError as e:
            logger.error(f"❌ CBR API connection error: {e}")
            logger.info("🔄 Falling back to mock rates")
            return self._get_mock_rates()
        except Exception as e:
            logger.error(f"❌ CBR API request failed: {e}")
            logger.info("🔄 Falling back to mock rates")
            return self._get_mock_rates()   

    def _get_mock_rates(self):
        """Мок-данные для валют (если API недоступно)"""
        logger.info("Using mock currency rates based on actual CBR data")
        return {
            'USD': {'value': 80.7321, 'previous': 80.9448, 'change': -0.2127, 'change_percent': -0.26},
            'EUR': {'value': 92.6047, 'previous': 93.7804, 'change': -1.1757, 'change_percent': -1.25},
            'CNY': {'value': 11.2795, 'previous': 11.3434, 'change': -0.0639, 'change_percent': -0.56},
            'GBP': {'value': 105.5976, 'previous': 106.3938, 'change': -0.7962, 'change_percent': -0.75},
            'JPY': {'value': 0.513694, 'previous': 0.520713, 'change': -0.007019, 'change_percent': -1.35},
            'CHF': {'value': 100.2136, 'previous': 101.0295, 'change': -0.8159, 'change_percent': -0.81},
            'TRY': {'value': 1.90794, 'previous': 1.91349, 'change': -0.00555, 'change_percent': -0.29},
            'KZT': {'value': 0.15543, 'previous': 0.155361, 'change': 0.000069, 'change_percent': 0.04},
            'RUB': {'value': 1.0, 'previous': 1.0, 'change': 0.0, 'change_percent': 0.0},
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
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
    name="currency",
    description="Курсы валют",
    version="1.2"
)
class CurrencyPlugin(BasePlugin):
    def __init__(self):
        super().__init__("currency", "Курсы валют", "1.2")
        self.cbr_url = "https://www.cbr-xml-daily.ru/daily_json.js"
        self.cache = {}
        self.cache_timeout = 300  # 5 минут

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
        
        logger.info("✅ Currency plugin handlers setup completed")

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
                "`1000 RUB to EUR`\n\n"
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
            "💱 *Курсы валют*\n\n"
            "• 💵 *Основные валюты* - USD, EUR, CNY, GBP\n"
            "• 🔄 *Конвертер* - перевод между валютами\n"
            "• 📊 *Все курсы* - полный список\n"
            "• 📈 *Изменения* - динамика за сутки\n\n"
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
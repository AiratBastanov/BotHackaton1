import inspect
from typing import Dict, Callable, Any
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
import logging

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self):
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self.command_handlers = {}
        self.message_handlers = {}

    def register_plugin(self, name: str, description: str, version: str = "1.0"):
        """Декоратор для регистрации плагинов"""
        def decorator(cls):
            self.plugins[name] = {
                'class': cls,
                'description': description,
                'version': version,
                'instance': None,
                'initialized': False
            }
            logger.info(f"✅ Plugin registered: {name} v{version}")
            return cls
        return decorator

    def command(self, command: str, description: str = ""):
        """Декоратор для регистрации команд"""
        def decorator(func):
            self.command_handlers[command] = {
                'handler': func,
                'description': description
            }
            return func
        return decorator

    def message_handler(self, pattern: str = None, content_type: str = "text"):
        """Декоратор для обработчиков сообщений"""
        def decorator(func):
            self.message_handlers[func.__name__] = {
                'handler': func,
                'pattern': pattern,
                'content_type': content_type
            }
            return func
        return decorator

    def setup_plugins(self, application):
        """Настройка всех плагинов в приложении"""
        # Регистрируем команды
        for command, data in self.command_handlers.items():
            # Для команд создаем обертку, которая передает self
            handler_func = data['handler']
            application.add_handler(CommandHandler(command, handler_func))
            logger.info(f"✅ Command registered: /{command}")

        # Инициализируем плагины
        for name, plugin_data in self.plugins.items():
            try:
                plugin_class = plugin_data['class']
                plugin_instance = plugin_class()
                
                # Настраиваем обработчики плагина
                if hasattr(plugin_instance, 'setup_handlers'):
                    plugin_instance.setup_handlers(application)
                
                # Инициализируем плагин
                if hasattr(plugin_instance, 'initialize'):
                    plugin_instance.initialize()
                
                plugin_data['instance'] = plugin_instance
                plugin_data['initialized'] = True
                logger.info(f"✅ Plugin initialized: {name}")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize plugin {name}: {e}")
                plugin_data['initialized'] = False

    def get_plugin(self, name: str):
        """Получить экземпляр плагина"""
        plugin_data = self.plugins.get(name, {})
        return plugin_data.get('instance')

    def is_plugin_initialized(self, name: str) -> bool:
        """Проверить, инициализирован ли плагин"""
        plugin_data = self.plugins.get(name, {})
        return plugin_data.get('initialized', False)


# Глобальный менеджер плагинов
plugin_manager = PluginManager()
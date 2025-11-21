from abc import ABC, abstractmethod
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    """Базовый класс для всех плагинов"""
    
    def __init__(self, name: str, description: str, version: str = "1.0"):
        self.name = name
        self.description = description
        self.version = version
        self.initialized = False
        self.user_data: Dict[int, Any] = {}  # Хранение данных пользователей

    @abstractmethod
    def setup_handlers(self, application):
        """Настройка обработчиков плагина - должен быть реализован в дочерних классах"""
        pass

    def initialize(self):
        """Инициализация плагина"""
        try:
            self._on_initialize()
            self.initialized = True
            logger.info(f"✅ Plugin initialized: {self.name} v{self.version}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize plugin {self.name}: {e}")
            raise

    def _on_initialize(self):
        """Внутренний метод инициализации, может быть переопределен"""
        pass

    def get_user_data(self, user_id: int) -> Dict:
        """Получить данные пользователя"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
        return self.user_data[user_id]

    def set_user_data(self, user_id: int, data: Dict):
        """Установить данные пользователя"""
        self.user_data[user_id] = data

    def cleanup_user_data(self, user_id: int):
        """Очистить данные пользователя"""
        self.user_data.pop(user_id, None)

    def is_initialized(self) -> bool:
        """Проверка инициализации"""
        return self.initialized

    def get_info(self) -> Dict[str, str]:
        """Получить информацию о плагине"""
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'initialized': self.initialized
        }
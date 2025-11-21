import asyncio
import os
import json
import hashlib
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self):
        self.redis_client = None
        self.memory_cache = {}
        self._init_redis()

    def _init_redis(self):
        """Инициализация Redis клиента"""
        try:
            import redis
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=0,
                decode_responses=True
            )
            # Проверяем подключение
            self.redis_client.ping()
            logger.info("✅ Redis connected successfully")
        except ImportError:
            logger.warning("❌ Redis not installed. Using memory cache.")
            self.redis_client = None
        except Exception as e:
            logger.warning(f"❌ Redis not available: {e}. Using memory cache.")
            self.redis_client = None

    async def get(self, key: str) -> Optional[str]:
        """Получить значение из кеша"""
        try:
            if self.redis_client:
                return self.redis_client.get(key)
            else:
                return self.memory_cache.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    async def set(self, key: str, value: str, expire: int = 3600):
        """Установить значение в кеш"""
        try:
            if self.redis_client:
                self.redis_client.setex(key, expire, value)
            else:
                self.memory_cache[key] = value
        except Exception as e:
            logger.error(f"Cache set error: {e}")

    async def delete(self, key: str):
        """Удалить значение из кеш"""
        try:
            if self.redis_client:
                self.redis_client.delete(key)
            else:
                self.memory_cache.pop(key, None)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")


class RetryManager:
    """Менеджер повторных попыток для API вызовов"""

    @staticmethod
    def ai_api_retry():
        """Retry декоратор для AI API"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                for attempt in range(3):
                    try:
                        return await func(*args, **kwargs)
                    except (Exception, asyncio.TimeoutError) as e:
                        if attempt == 2:  # Последняя попытка
                            raise e
                        wait_time = 2 ** attempt  # Экспоненциальная backoff
                        logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                return await func(*args, **kwargs)
            return wrapper
        return decorator

    @staticmethod
    def weather_api_retry():
        """Retry декоратор для Weather API"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                for attempt in range(2):
                    try:
                        return await func(*args, **kwargs)
                    except (Exception, asyncio.TimeoutError) as e:
                        if attempt == 1:  # Последняя попытка
                            raise e
                        wait_time = 1  # Фиксированная задержка
                        logger.warning(f"Weather API attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                return await func(*args, **kwargs)
            return wrapper
        return decorator


def cached(key_pattern: str, expire: int = 3600):
    """Декоратор для кеширования результатов функций"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Генерируем ключ кеша
            key_data = f"{key_pattern}:{str(args)}:{str(kwargs)}"
            cache_key = hashlib.md5(key_data.encode()).hexdigest()
            
            # Пробуем получить из кеша
            cache_manager = CacheManager()
            cached_result = await cache_manager.get(cache_key)
            
            if cached_result:
                logger.info(f"Cache HIT for {key_pattern}")
                return json.loads(cached_result)
            
            # Вызываем функцию и кешируем результат
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, json.dumps(result), expire)
            
            return result
        return wrapper
    return decorator


# Глобальные экземпляры
cache_manager = CacheManager()
retry_manager = RetryManager()
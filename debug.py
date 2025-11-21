import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 ДИАГНОСТИКА КОНФИГУРАЦИИ")
print("=" * 50)

# Проверяем переменные окружения
bot_token = os.getenv("BOT_TOKEN")
deepseek_key = os.getenv("DEEPSEEK_API_KEY")

print(f"BOT_TOKEN: {bot_token}")
print(f"DEEPSEEK_API_KEY: {deepseek_key}")

print(f"BOT_TOKEN exists: {bool(bot_token)}")
print(f"DEEPSEEK_API_KEY exists: {bool(deepseek_key)}")

# Проверяем импорты
try:
    from utils.text_filter import TextFilter
    print("✅ TextFilter import: УСПЕХ")
except ImportError as e:
    print(f"❌ TextFilter import: ОШИБКА - {e}")

try:
    from utils.context_manager import ContextManager
    print("✅ ContextManager import: УСПЕХ")
except ImportError as e:
    print(f"❌ ContextManager import: ОШИБКА - {e}")

print("=" * 50)
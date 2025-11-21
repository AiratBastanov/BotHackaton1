import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Bot settings
MAX_HISTORY_LENGTH = 10
PROFANITY_FILTER_ENABLED = True

# Context settings
CONTEXT_TIMEOUT = 900  # 15 minutes in seconds

# Docker/Environment settings
IS_DOCKER = os.getenv("IS_DOCKER", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Validation
def validate_config():
    errors = []
    
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN не настроен в .env файле")
    elif BOT_TOKEN == "8566890832:AAGAlozLDSFAymfhCTI2iSkJQPwO4p2p1W8":
        errors.append("BOT_TOKEN установлен в значение по умолчанию. Используйте ваш реальный токен")
    
    if not DEEPSEEK_API_KEY:
        errors.append("DEEPSEEK_API_KEY не настроен в .env файле")
    elif "your_actual" in DEEPSEEK_API_KEY:
        errors.append("DEEPSEEK_API_KEY установлен в значение по умолчанию. Получите ключ на https://platform.deepseek.com/")
    
    return errors
import time
import logging
from typing import Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    user_id: int
    user_name: str = ""
    messages: List[dict] = None
    created_at: float = None
    last_activity: float = None
    current_file_text: str = None
    current_file_type: str = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.created_at is None:
            self.created_at = time.time()
        if self.last_activity is None:
            self.last_activity = time.time()

    def add_message(self, role: str, content: str):
        """Добавить сообщение в историю"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
        self.last_activity = time.time()

        if len(self.messages) > 20:
            self.messages = self.messages[-20:]

    def get_conversation_history(self, max_messages: int = 10) -> List[dict]:
        """Получить историю разговора для AI"""
        recent_messages = self.messages[-max_messages:]
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in recent_messages
        ]

    def reset(self):
        """Сбросить контекст"""
        self.messages = []
        self.current_file_text = None
        self.current_file_type = None
        self.last_activity = time.time()
        logger.info(f"Context reset for user {self.user_id}")

    def is_expired(self, timeout: int = 1800) -> bool:
        """Проверить, истекло ли время контекста"""
        return (time.time() - self.last_activity) > timeout


class ContextManager:
    def __init__(self):
        self.user_contexts: Dict[int, UserContext] = {}

    def get_user_context(self, user_id: int) -> UserContext:
        """Получить или создать контекст пользователя"""
        self._cleanup_expired_contexts()

        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = UserContext(user_id=user_id)
            logger.info(f"Created new context for user {user_id}")

        return self.user_contexts[user_id]

    def _cleanup_expired_contexts(self):
        """Очистить устаревшие контексты"""
        current_time = time.time()
        expired_users = [
            user_id for user_id, context in self.user_contexts.items()
            if context.is_expired()
        ]

        for user_id in expired_users:
            del self.user_contexts[user_id]
            logger.info(f"Cleaned up expired context for user {user_id}")

    def get_stats(self) -> dict:
        """Получить статистику по контекстам"""
        return {
            "total_users": len(self.user_contexts),
            "active_users": len([
                uid for uid, ctx in self.user_contexts.items()
                if not ctx.is_expired(300)
            ])
        }
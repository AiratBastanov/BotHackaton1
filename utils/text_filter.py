import re
import string
from typing import Tuple, List, Dict
import logging
from collections import Counter

logger = logging.getLogger(__name__)


class UltraTextFilter:
    def __init__(self):
        # ОСНОВНЫЕ МАТЕРНЫЕ СЛОВА (только явные матерные слова)
        self.base_profanity = [
            # Русские матерные слова (только самые явные)
            'хуй', 'хуё', 'хуя', 'пизд', 'ебан', 'ебать', 'ёбан', 'ёбать',
            'блядь', 'бляд', 'гандон', 'мудак', 'пидор', 'педик',
            'шлюха', 'проститутка', 'ебал', 'залупа', 'манда',
            'долбоёб', 'уебан', 'выебан', 'выеб',

            # Английские матерные слова
            'fuck', 'shit', 'asshole', 'bitch', 'cunt', 'dick', 'pussy',
            'whore', 'slut', 'bastard', 'motherfucker', 'cock', 'nigger',
            'faggot', 'prick'
        ]

        # СЛОВА-МАСКИ (замена букв) - только для явных замен
        self.leet_replacements = {
            'a': ['4', '@'], 'e': ['3'], 'i': ['1', '!'],
            'o': ['0'], 's': ['5', '$'], 't': ['7'],
            'b': ['8'], 'g': ['9'], 'l': ['1', '|'],
            'z': ['2']
        }

        # РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ДЛЯ СЛОЖНЫХ ПАТТЕРНОВ
        self.patterns = {
            # Основные матерные паттерны (более точные)
            'russian_profanity': r'(?i)([хx][уy][йj]|[пp][иi][з3][дd]|[еe][б6][аa])',
            'english_profanity': r'(?i)\b(fuck|shit|asshole|bitch|cunt|dick|pussy|whore)\b',

            # Ссылки и контакты
            'urls': r'(https?://|www\.|t\.me/|@[\w]+|vk\.com/|instagram\.com/)[^\s]*',
            'emails': r'\b[\w\.-]+@[\w\.-]+\.\w+\b',
            'phones': r'[\+]?[0-9\s\-\(\)]{10,}',  # минимум 10 цифр

            # Спам и реклама (более точные паттерны)
            'spam_keywords': r'(?i)\b(купите|покупайте|заказывайте|акция|скидка|распродажа|бесплатно|заработок)\b',
            'crypto': r'(?i)\b(криптовалют[ауы]|биткоин|блокчейн|nft|эфириум)\b',
            'casino': r'(?i)\b(казино|ставк[иа]|покер|лотере[яи]|выигрыш)\b',

            # Капс и повторения
            'caps': r'\b[A-ZА-Я]{4,}\b',  # только целые слова в капсе
            'repetitive': r'(.)\1{5,}',   # 6+ повторений символа
            'excessive_punct': r'[!?]{4,}', # 4+ восклицательных знаков

            # Личные данные
            'personal_info': r'\b(?:\d{16}|\d{3}-\d{2}-\d{4}|\b[A-Z][a-z]+ [A-Z][a-z]+\b)\b'
        }

        # КОНТЕКСТНЫЕ ТРИГГЕРЫ (только явно опасные)
        self.context_triggers = {
            'scam': ['гарантирован', 'быстрый доход', 'легкие деньги', 'прибыль'],
            'adult': ['порно', 'интим', 'голый', 'обнаженный', 'xxx'],
            'violence': ['убийство', 'оружие', 'насилие', 'избиение'],
            'drugs': ['наркотик', 'марихуана', 'героин', 'кокаин', 'лсд'],
            'hate_speech': ['ненависть', 'убивай', 'смерть', 'терроризм']
        }

        # БЕЛЫЙ СПИСОК - слова, которые могут быть ошибочно заблокированы
        self.whitelist = [
            'хер', 'хрен', 'сука', 'суки', 'блять',  # смягченные варианты
            'секс', 'интимный', 'обнаженка',         # контекстные слова
            'биткоин', 'блокчейн', 'нфт',           # крипто термины
            'казин', 'покер',                      # игровые термины
            'купить', 'покупать', 'заказ', 'бизнес', # коммерческие термины
            'очистка', 'таймер', 'контекст', 'память', # технические термины
            'бот', 'промпт', 'python', 'код', 'шаблон',
            'клавиатуры', 'replykeyboardmarkup', 'inlinekeyboardmarkup',
            'кнопка', 'меню', 'сбросить', 'диалог',
            'автоперезагрузка', 'watchdog', 'разработка', 'дебаг',
            'openai', 'hf', 'модель', 'диалог', 'настройки',
            'redis', 'memory', 'context', 'пользователь',
            'rate', 'limiting', 'спам', 'ddos', 'нагрузка', 'api'
        ]

    def filter_text(self, text: str) -> Tuple[str, str]:
        """УЛЬТРА-фильтрация текста"""
        if not text or len(text.strip()) < 2:
            return "", "сообщение слишком короткое"

        if len(text) > 2000:
            return "", "сообщение слишком длинное"

        # Проверяем белый список ПЕРВЫМ делом
        if self._check_whitelist(text):
            return text, ""

        # Нормализуем текст для анализа
        normalized_text = self._normalize_text(text.lower())

        # МНОГОУРОВНЕВАЯ ПРОВЕРКА
        checks = [
            self._check_profanity(normalized_text, text),
            self._check_links(text),
            self._check_spam(normalized_text),
            self._check_suspicious_patterns(text),
            self._check_context(normalized_text),
            self._check_behavior(text)
        ]

        for error_type, error_msg in checks:
            if error_type:
                logger.warning(f"Text blocked: {error_type} - {error_msg} - Text: {text}")
                return "", f"{error_type}: {error_msg}"

        return text, ""

    def _check_whitelist(self, text: str) -> bool:
        """Проверка белого списка"""
        text_lower = text.lower()
        # Разбиваем на слова и проверяем каждое слово отдельно
        words = re.findall(r'\b\w+\b', text_lower)
        for word in words:
            if word in self.whitelist:
                return True
        return False

    def _normalize_text(self, text: str) -> str:
        """Нормализация текста для поиска скрытых нарушений"""
        # Заменяем leet-speak на нормальные буквы (только для английских букв)
        normalized = text
        for normal_char, replacements in self.leet_replacements.items():
            for replacement in replacements:
                normalized = normalized.replace(replacement, normal_char)

        # Удаляем лишние символы для поиска скрытых слов
        cleaned = re.sub(r'[^\w\s]', '', normalized)
        return cleaned

    def _check_profanity(self, normalized_text: str, original_text: str) -> Tuple[str, str]:
        """Проверка нецензурной лексики (включая скрытую)"""
        # Проверка базовых слов (только полные слова)
        words = normalized_text.split()
        for word in words:
            for profanity in self.base_profanity:
                # Проверяем точное совпадение или вхождение в слово
                if profanity == word or (profanity in word and len(word) <= len(profanity) + 2):
                    # Дополнительная проверка на случайные совпадения
                    if len(word) >= 3:  # только слова длиной от 3 символов
                        return "нецензурная лексика", f"обнаружено запрещенное слово"

        # Проверка по регулярным выражениям
        for pattern_name, pattern in self.patterns.items():
            if 'profanity' in pattern_name and re.search(pattern, original_text.lower()):
                # Проверяем, что это не часть другого слова
                matches = re.finditer(pattern, original_text.lower())
                for match in matches:
                    matched_text = match.group()
                    # Проверяем, что это отдельное слово или явный мат
                    if len(matched_text) >= 3:
                        return "нецензурная лексика", "обнаружены запрещенные выражения"

        # Проверка замаскированных слов (с символами между буквами)
        if self._check_hidden_profanity(original_text):
            return "нецензурная лексика", "обнаружены скрытые запрещенные слова"

        return "", ""

    def _check_hidden_profanity(self, text: str) -> bool:
        """Проверка скрытой нецензурной лексики"""
        # Удаляем все не-буквенные символы и проверяем
        letters_only = re.sub(r'[^a-zA-Zа-яА-Я]', '', text.lower())

        # Проверяем наличие матерных корней (только в отдельных словах)
        profanity_roots = ['хуй', 'пизд', 'еба', 'бляд']  # только явные корни
        words = re.findall(r'\w+', letters_only)
        
        for word in words:
            for root in profanity_roots:
                if root in word and len(word) <= len(root) + 2:  # допускаем небольшие вариации
                    return True

        return False

    def _check_links(self, text: str) -> Tuple[str, str]:
        """Проверка ссылок и контактов"""
        for pattern_name, pattern in self.patterns.items():
            if pattern_name in ['urls', 'emails', 'phones']:
                matches = re.findall(pattern, text)
                if matches:
                    # Игнорируем простые @упоминания без доменов
                    if pattern_name == 'urls':
                        filtered_matches = [m for m in matches if not (m.startswith('@') and '/' not in m)]
                        if filtered_matches:
                            return "ссылки/контакты", "обнаружены ссылки или контактные данные"
                    else:
                        return "ссылки/контакты", "обнаружены ссылки или контактные данные"

        return "", ""

    def _check_spam(self, normalized_text: str) -> Tuple[str, str]:
        """Проверка спама и рекламы"""
        spam_indicators = 0

        # Проверка ключевых слов спама (только в контексте)
        for pattern_name, pattern in self.patterns.items():
            if pattern_name in ['spam_keywords', 'crypto', 'casino']:
                if re.search(pattern, normalized_text):
                    spam_indicators += 1

        # Требуем больше индикаторов для блокировки
        if spam_indicators >= 3:
            return "рекламный спам", "обнаружены признаки рекламы или спама"

        return "", ""

    def _check_suspicious_patterns(self, text: str) -> Tuple[str, str]:
        """Проверка подозрительных паттернов"""
        # Капслок - только если много слов в капсе
        caps_words = re.findall(self.patterns['caps'], text)
        if len(caps_words) >= 3:  # минимум 3 слова в капсе
            return "капслок", "сообщение написано капсом"

        # Повторения символов
        if re.search(self.patterns['repetitive'], text):
            return "повторения", "слишком много повторяющихся символов"

        # Избыточная пунктуация
        if re.search(self.patterns['excessive_punct'], text):
            return "пунктуация", "слишком много восклицательных/вопросительных знаков"

        # Личные данные
        if re.search(self.patterns['personal_info'], text):
            return "личные данные", "обнаружены личные данные"

        return "", ""

    def _check_context(self, normalized_text: str) -> Tuple[str, str]:
        """Контекстная проверка"""
        for category, triggers in self.context_triggers.items():
            found_triggers = []
            for trigger in triggers:
                # Ищем целые слова, а не части слов
                if re.search(r'\b' + re.escape(trigger) + r'\b', normalized_text):
                    found_triggers.append(trigger)

            # Требуем больше триггеров для блокировки
            if len(found_triggers) >= 3:
                category_names = {
                    'scam': 'мошенничество',
                    'adult': 'взрослый контент',
                    'violence': 'контент о насилии',
                    'drugs': 'наркотики',
                    'hate_speech': 'разжигание ненависти'
                }
                return category_names.get(category, 'неподходящий контент'), f"обнаружены признаки {category}"

        return "", ""

    def _check_behavior(self, text: str) -> Tuple[str, str]:
        """Поведенческий анализ"""
        words = text.split()

        # Проверка на флуд (много повторяющихся слов)
        if len(words) > 15:  # увеличил минимальную длину
            word_freq = Counter(words)
            most_common = word_freq.most_common(1)[0]
            if most_common[1] > len(words) * 0.4:  # 40% повторений (было 30%)
                return "флуд", "слишком много повторяющихся слов"

        # Проверка на специальные символы
        special_chars = len(re.findall(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?]', text))
        if special_chars > len(text) * 0.5:  # 50% спецсимволов (было 40%)
            return "спецсимволы", "слишком много специальных символов"

        return "", ""

    def is_unclear_message(self, text: str) -> bool:
        """Проверка неясных запросов"""
        unclear_patterns = [
            r'^\s*[чкп]\s*$',
            r'^\s*[?¿]\s*$',
            r'^\s*\.+\s*$',
            r'^\s*[нт]ет\s*$'
        ]

        for pattern in unclear_patterns:
            if re.match(pattern, text.lower()):
                return True

        short_unclear = ['что', 'как', 'почему', 'зачем', 'кто', 'где']
        words = text.lower().split()
        return len(words) <= 2 and any(word in short_unclear for word in words)

    def get_detailed_report(self, text: str) -> Dict:
        """Детальный отчет о проверке (для отладки)"""
        normalized = self._normalize_text(text.lower())

        return {
            'original_length': len(text),
            'normalized_text': normalized,
            'profanity_check': self._check_profanity(normalized, text),
            'links_check': self._check_links(text),
            'spam_check': self._check_spam(normalized),
            'suspicious_check': self._check_suspicious_patterns(text),
            'context_check': self._check_context(normalized),
            'behavior_check': self._check_behavior(text),
            'is_unclear': self.is_unclear_message(text),
            'whitelist_check': self._check_whitelist(text)
        }


# Глобальный экземпляр фильтра
text_filter = UltraTextFilter()
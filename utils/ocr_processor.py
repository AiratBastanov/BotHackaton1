import os
import base64
import aiohttp
import logging
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)


class OCRProcessor:
    def __init__(self):
        self.use_api = os.getenv("USE_OCR_API", "false").lower() == "true"
        self.api_key = os.getenv("OCR_API_KEY")

    async def extract_text_from_image(self, file_content: bytes) -> str:
        """Извлечение текста из изображения через API или локально"""
        if self.use_api and self.api_key:
            return await self._extract_via_api(file_content)
        else:
            return await self._extract_via_local(file_content)

    async def _extract_via_api(self, file_content: bytes) -> str:
        """Использование OCR.space API"""
        try:
            url = "https://api.ocr.space/parse/image"

            # Кодируем изображение в base64
            base64_image = base64.b64encode(file_content).decode()

            payload = {
                'base64Image': f'data:image/jpeg;base64,{base64_image}',
                'language': 'rus+eng',
                'isOverlayRequired': False,
                'OCREngine': 2
            }

            headers = {
                'apikey': self.api_key
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=payload, headers=headers) as response:
                    result = await response.json()

                    if result.get("IsErroredOnProcessing"):
                        error_message = result.get("ErrorMessage", "Unknown OCR error")
                        raise Exception(f"OCR API error: {error_message}")

                    parsed_results = result.get("ParsedResults", [])
                    if parsed_results:
                        return parsed_results[0].get("ParsedText", "").strip()
                    else:
                        return ""

        except Exception as e:
            logger.error(f"OCR API error: {e}")
            # Пробуем локальный метод как fallback
            return await self._extract_via_local(file_content)

    async def _extract_via_local(self, file_content: bytes) -> str:
        """Локальное распознавание с улучшенной обработкой ошибок"""
        try:
            # Пробуем импортировать pytesseract
            try:
                import pytesseract
            except ImportError:
                raise Exception("pytesseract не установлен. Установите: pip install pytesseract")

            # Проверяем доступность Tesseract
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                raise Exception("Tesseract не установлен или не найден в PATH")

            # Обрабатываем изображение
            image = Image.open(BytesIO(file_content))

            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Пробуем разные языки и настройки
            languages_to_try = ['rus+eng', 'eng', 'rus']

            for lang in languages_to_try:
                try:
                    custom_config = r'--oem 3 --psm 6'
                    text = pytesseract.image_to_string(image, lang=lang, config=custom_config)
                    if text.strip():
                        return text.strip()
                except Exception as e:
                    logger.warning(f"Tesseract failed for language {lang}: {e}")
                    continue

            # Если все языки не сработали, пробуем без указания языка
            try:
                text = pytesseract.image_to_string(image, config='--oem 3 --psm 6')
                return text.strip()
            except Exception as e:
                raise Exception(f"Все попытки распознавания не удались: {e}")

        except Exception as e:
            logger.error(f"Local OCR error: {e}")
            raise Exception(f"Ошибка локального распознавания: {e}")


# Глобальный экземпляр процессора
ocr_processor = OCRProcessor()
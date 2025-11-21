import os
import aiohttp
import logging
import speech_recognition as sr
from io import BytesIO
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class VoiceProcessor:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.use_api = os.getenv("USE_SPEECH_API", "false").lower() == "true"
        
        # Настраиваем распознаватель для лучшего качества
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8
        self.recognizer.dynamic_energy_threshold = True

    async def speech_to_text(self, voice_file_content: bytes) -> str:
        """Конвертирует голосовое сообщение в текст"""
        try:
            logger.info("Начинаю обработку голосового сообщения...")
            
            # Конвертируем OGG в WAV
            audio = AudioSegment.from_ogg(BytesIO(voice_file_content))
            wav_buffer = BytesIO()
            audio.export(wav_buffer, format="wav")
            wav_buffer.seek(0)

            # Распознаем речь
            with sr.AudioFile(wav_buffer) as source:
                # Убираем фоновый шум
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = self.recognizer.record(source)
                
                logger.info("Пробую распознать речь...")
                
                # Пробуем разные сервисы распознавания
                try:
                    text = self.recognizer.recognize_google(audio_data, language='ru-RU')
                    logger.info(f"Успешно распознано: {text}")
                    return text.strip()
                except sr.UnknownValueError:
                    logger.warning("Google Speech Recognition не смог распознать аудио (русский)")
                    try:
                        text = self.recognizer.recognize_google(audio_data, language='en-US')
                        logger.info(f"Успешно распознано (английский): {text}")
                        return text.strip()
                    except sr.UnknownValueError:
                        logger.warning("Google Speech Recognition не смог распознать аудио (английский)")
                        return "Не удалось распознать речь"
                except sr.RequestError as e:
                    logger.error(f"Ошибка запроса к Google Speech Recognition: {e}")
                    return "Ошибка сервиса распознавания речи"
                except Exception as e:
                    logger.error(f"Неожиданная ошибка распознавания: {e}")
                    return "Ошибка распознавания речи"

        except Exception as e:
            logger.error(f"Ошибка обработки голоса: {e}")
            return f"Ошибка обработки голоса: {e}"

    async def process_voice_message(self, voice_content: bytes) -> dict:
        """Обрабатывает голосовое сообщение и возвращает результат"""
        text = await self.speech_to_text(voice_content)
        
        success = bool(text and text not in [
            "Не удалось распознать речь", 
            "Ошибка сервиса распознавания речи",
            "Ошибка распознавания речи"
        ] and not text.startswith("Ошибка обработки голоса"))
        
        return {
            "success": success,
            "text": text,
            "length": len(text) if text else 0
        }

# Глобальный экземпляр процессора
voice_processor = VoiceProcessor()
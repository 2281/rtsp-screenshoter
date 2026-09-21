from datetime import datetime
import json
import logging
from pathlib import Path
import subprocess
import time




with open('C:\\Aegis\\rtsp-screenshoter\\config.json', 'r') as config_file:
    config = json.load(config_file)


LOG_DIR = Path(config.get('LOG_DIR'))
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file():
    return LOG_DIR / f"{datetime.now():%Y%m}.log"


class MonthlyFileHandler(logging.Handler):
    """
    Handler, который записывает логи в файл текущего месяца.
    При смене месяца автоматически переключается на новый файл.
    """

    def __init__(self):
        super().__init__()
        self.current_file = None
        self.file_handler = None
        self._update_handler()

    def _update_handler(self):
        log_file = get_log_file()

        if self.current_file != log_file:
            if self.file_handler:
                self.file_handler.close()

            self.current_file = log_file

            self.file_handler = logging.FileHandler(
                log_file,
                encoding="utf-8"
            )

            self.file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            )

    def emit(self, record):
        self._update_handler()
        self.file_handler.emit(record)

    def close(self):
        if self.file_handler:
            self.file_handler.close()

        super().close()


logger = logging.getLogger("ffmpeg_capture")
logger.setLevel(logging.INFO)

# Не передавать сообщения родительскому logger
logger.propagate = False


# Лог в файл
file_handler = MonthlyFileHandler()
logger.addHandler(file_handler)


# Лог одновременно в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
)
logger.addHandler(console_handler)


creation_flags = subprocess.CREATE_NO_WINDOW

FFMPEG = config.get('FFMPEG')
FPS = config.get('FPS')
IP = config.get('IP')
PORT = config.get('PORT')
PARAMS = config.get('PARAMS')
PASSWORD = config.get('PASSWORD')


RTSP_URL = f'rtsp://admin:{PASSWORD}@{IP}:{PORT}/{PARAMS}'


logger.info(
    f'RTSP_URL: rtsp://login:password@{IP}:{PORT}/{PARAMS}'
)


OUTPUT_DIR = Path('C:\\Aegis\\core\\screenshots\\')
OUTPUT_FILE = OUTPUT_DIR / "actual.jpg"

OUTPUT_PATTERN = OUTPUT_DIR / '%d.jpg'
# FRAMES_PER_CYCLE = 10  # кадров за цикл (10 fps = каждые 100 мс)


def run_ffmpeg_persistent():
    """
    Постоянно читает RTSP через FFmpeg со скоростью FPS кадров/сек.
    Кадры сохраняются циклически в:
        0.jpg
        1.jpg
        ...
        9.jpg

    При падении FFmpeg автоматически перезапускается.
    """

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fps = int(FPS)
 
    cmd = [
        FFMPEG,

        '-hide_banner',
        '-loglevel', 'warning',
        '-rtsp_transport', 'tcp',
        '-timeout', '5000000',
        '-i', RTSP_URL,
        '-vf', f'fps={FPS}',
        '-an',
        '-c:v', 'mjpeg',
        '-q:v', '5',
        '-f', 'image2pipe',
        '-',
    ]


    logger.info(
        f'Запуск постоянного захвата ({fps} кадров/сек). Ctrl+C для остановки.'
    )

    while True:

        proc = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=creation_flags,
            )

            logger.info(
                f'ffmpeg запущен (PID {proc.pid})'
            )

            frame_counter = 0
            buffer = bytearray()

            while True:

                chunk = proc.stdout.read(16384)

                if not chunk:
                    # stdout закрыт — FFmpeg завершился
                    break

                buffer.extend(chunk)

                while True:

                    start = buffer.find(b'\xff\xd8')

                    if start == -1:
                        # JPEG start marker не найден
                        buffer.clear()
                        break

                    end = buffer.find(
                        b'\xff\xd9',
                        start + 2
                    )

                    if end == -1:
                        # JPEG не полностью получен
                        if start > 0:
                            del buffer[:start]

                        break

                    end += 2

                    frame_data = bytes(
                        buffer[start:end]
                    )

                    del buffer[:end]

                    # 0.jpg ... 9.jpg
                    file_idx = frame_counter % fps

                    file_path = OUTPUT_DIR / f'{file_idx}.jpg'

                    with open(file_path, 'wb') as f:
                        f.write(frame_data)

                    frame_counter += 1

        except subprocess.CalledProcessError:
            logger.exception("Ошибка самого FFmpeg при обработке видеопотока...")
            continue

        finally:

            if proc is not None:

                # Если процесс ещё работает — останавливаем
                if proc.poll() is None:
                    proc.terminate()

                ret = proc.wait()

                # Читаем stderr после завершения
                err = proc.stderr.read()

                err_text = err.decode(
                    errors='replace'
                ).strip()

                logger.warning(
                    f'ffmpeg завершился (код {ret}). Перезапуск...'
                )

                if err_text:
                    logger.error(
                        f'FFmpeg: {err_text[-1000:]}'
                    )

        # Небольшая пауза перед повторным запуском
        # time.sleep(1)


if __name__ == "__main__":
    try:
        run_ffmpeg_persistent()

    except KeyboardInterrupt:
        logger.info("Остановлено пользователем.")

    finally:
        logging.shutdown()

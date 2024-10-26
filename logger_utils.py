import logging
from logging import handlers

class LoggingManager:
    def __init__(self):
        logging.basicConfig(level='INFO', format='[%(asctime)s][%(name)s][%(levelname)s] %(message)s',
                            datefmt='%d-%m-%y %H:%M:%S')

        self.__time_handler = handlers.TimedRotatingFileHandler(f'logs/api.log', when='midnight', interval=1,
                                                         backupCount=7)
        self.__time_handler.setLevel('INFO')
        self.__time_handler.setFormatter(
            logging.Formatter('[%(asctime)s][%(name)s][%(levelname)s] %(message)s', datefmt='%d-%m-%y %H:%M:%S'))
        logging.getLogger().addHandler(self.__time_handler)

        self.__logger = logging.getLogger()

    def get(self):
        return self.__logger

    def set_log_level(self, level):
        self.__logger.setLevel(level)
        self.__time_handler.setLevel(level)

    def set_logs_rotation(self, count):
        self.__time_handler.backupCount = count
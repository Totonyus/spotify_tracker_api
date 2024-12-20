import configparser

from logger_utils import LoggingManager

from apscheduler.triggers.cron import CronTrigger

default_params = {
    'cliend_id': None,
    'client_secret': None,
    'application_url': 'http://localhost:8000',

    'listen_port': 8000,
    'listen_host': '0.0.0.0',
    'log_level': 'INFO',
    'logs_rotation': 7,

    'albums_request_limit': 5,
    'delay': 0,
    'newer_than': 30,
    'default_sorting': 'release_date_timestamp',
    'include_groups': ['album', 'single', 'compilation', 'appears_on'],

    'search_url_music': '',
    'search_url_shows': '',

    'cron': '0 1 * * *'
}

params_metadata = {
    'int': ['newer_than', 'delay', 'listen_port', 'albums_request_limit', 'logs_rotation'],
    'array': ['include_groups'],
    'cannot_be_none': ['client_id', 'client_secret', 'application_url'],
    'fixed_values': {
        'default_sorting': ['release_date_timestamp', 'added_date_timestamp']
    }
}


class ConfigManager:
    __parameters = {}

    def __init__(self):
        self.__app_config = configparser.ConfigParser(interpolation=None)
        self.__app_config.read('params/params.ini')

        self.__lu = LoggingManager()
        self.__log = self.__lu.get()

        self.__parse_parameters()

    def __parse_parameters(self):
        for option in self.__app_config['app']:
            if option in params_metadata.get('int'):
                try:
                    self.__parameters[option] = self.__app_config.getint(section='app', option=option)
                except ValueError:
                    self.get_logger().error(
                        f'params.ini : Value {option} must be an integer, using default value ({default_params.get(option)}) instead')
            elif option in params_metadata.get('array'):
                self.__parameters[option] = self.__app_config.get(section='app', option=option).split(',')
            else:
                self.__parameters[option] = self.__app_config.get(section='app', option=option)

        self.__parameters = default_params | self.__parameters

        for param in params_metadata.get('cannot_be_none'):
            if self.__parameters.get(param) is None or (
                    self.__parameters.get(param) is not None and self.__parameters.get(param) == ''):
                self.get_logger().fatal(
                    f'params.ini : Values {params_metadata.get("cannot_be_none")} cannot be None or empty, to know how to get those values : https://developer.spotify.com/documentation/web-api/tutorials/getting-started#create-an-app')
                exit(1)

        for param in params_metadata.get('fixed_values'):
            if self.__parameters.get(param) is None or (
                    self.__parameters.get(param) is not None and self.__parameters.get(
                param) not in params_metadata.get('fixed_values').get(param)):
                self.get_logger().error(
                    f'params.ini : {param} must be on those values : {params_metadata.get("fixed_values").get(param)}, found "{self.__parameters.get(param)}", fallback to default value : {default_params.get(param)}')
                self.__parameters[param] = default_params.get(param)

        try:
            CronTrigger.from_crontab(self.__parameters.get('cron'))
        except ValueError as e:
            self.get_logger().error(
                f'params.ini : Invalid cron configuration, fallback to default values ({default_params.get("cron")}) - {e}')
            self.__parameters['cron'] = default_params.get('cron')

        self.__lu.set_log_level(self.get('log_level'))
        self.__lu.set_logs_rotation(self.get('logs_rotation'))

    def get(self, parameter):
        return self.__parameters.get(parameter)

    def get_all(self):
        return self.__parameters

    def get_logger(self):
        return self.__log

    @staticmethod
    def get_metadata():
        return params_metadata

    @staticmethod
    def get_defaults():
        return default_params
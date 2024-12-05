import logging.config

from app.internal.http.middleware import get_correlation_id


class AppFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True


def setup_logging():
    logger = logging.getLogger()
    syslog = logging.StreamHandler()
    syslog.addFilter(AppFilter())
    formatter = logging.Formatter(
        '%(asctime)s loglevel=%(levelname)-6s logger=%(name)s %(funcName)s %(correlation_id)s %(message)s')
    syslog.setFormatter(formatter)
    logger.setLevel(logging.DEBUG if logging.DEBUG else logging.WARN)
    logger.addHandler(syslog)

"""MySQL repository placeholder.

The REST contract is intentionally independent of the storage implementation.
When the normalized WT8 rows are imported into MySQL, implement the methods
below and replace CsvRankingRepository in backend.routes.api.
"""
from .base import RankingRepository


class MySQLRankingRepository(RankingRepository):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("MySQL 数据仓储将在数据表结构确认后接入")

    def periods(self, limit=10000):
        raise NotImplementedError

    def contracts(self):
        raise NotImplementedError

    def ranking(self, timestamp, top_k=10):
        raise NotImplementedError

    def series(self, instrument):
        raise NotImplementedError

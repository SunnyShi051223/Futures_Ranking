from abc import ABC, abstractmethod


class RankingRepository(ABC):
    @abstractmethod
    def periods(self, limit: int = 10000):
        raise NotImplementedError

    @abstractmethod
    def contracts(self):
        raise NotImplementedError

    @abstractmethod
    def ranking(self, timestamp: str, top_k: int = 10, start_timestamp: str = None):
        raise NotImplementedError

    @abstractmethod
    def series(self, instrument: str, start_timestamp: str = None, end_timestamp: str = None):
        raise NotImplementedError

    @abstractmethod
    def trade_events(self, instrument: str, start_timestamp: str, end_timestamp: str):
        raise NotImplementedError

from abc import ABC, abstractmethod


class RankingRepository(ABC):
    @abstractmethod
    def periods(self, limit: int = 10000):
        raise NotImplementedError

    @abstractmethod
    def contracts(self):
        raise NotImplementedError

    @abstractmethod
    def ranking(self, timestamp: str, top_k: int = 10):
        raise NotImplementedError

    @abstractmethod
    def series(self, instrument: str):
        raise NotImplementedError

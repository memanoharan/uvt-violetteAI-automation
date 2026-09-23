from abc import ABC, abstractmethod
from src.models import JudgeResult


class Judge(ABC):
    @abstractmethod
    def evaluate(self, query: str, expected: str, actual: str) -> JudgeResult:
        raise NotImplementedError

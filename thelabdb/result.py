from typing import Literal


class _Either[_LT, _RT]:
    left: _LT
    right: _RT

    @property
    def is_left(self) -> bool:
        return False

    @property
    def is_right(self) -> bool:
        return False


class Left[_LT](_Either[_LT, None]):
    def __init__(self, value: _LT) -> None:
        self.left = value
        self.right = None

    @property
    def is_left(self) -> Literal[True]:
        return True

    @property
    def is_right(self) -> Literal[False]:
        return False


class Right[_RT](_Either[None, _RT]):
    def __init__(self, value: _RT) -> None:
        self.left = None
        self.right = value

    @property
    def is_left(self) -> Literal[False]:
        return False

    @property
    def is_right(self) -> Literal[True]:
        return True


type Either[_LT, _RT] = Left[_LT] | Right[_RT]

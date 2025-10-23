from .spread import SpreadFinder
from .models import BotMode


class Bot:
    def __init__(self, mode: BotMode):
        self.mode = mode
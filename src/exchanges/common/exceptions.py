class ExchangeError(Exception):
  pass


class InsufficientBalanceError(ExchangeError):
  pass


class InvalidSymbolError(ExchangeError):
  pass


class OrderError(ExchangeError):
  pass


class WebSocketError(ExchangeError):
  pass


class ConnectionError(ExchangeError):
  pass
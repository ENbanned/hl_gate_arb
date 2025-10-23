import os
from decimal import Decimal


from dotenv import load_dotenv
load_dotenv()


HYPERLIQUID_SECRET_KEY = os.getenv('HYPERLIQUID_SECRET_KEY')
HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv('HYPERLIQUID_ACCOUNT_ADDRESS')

GATE_API_KEY = os.getenv('GATE_API_KEY')
GATE_API_SECRET = os.getenv('GATE_API_SECRET')

GATE_TAKER_FEE = Decimal('0.0005')
HYPERLIQUID_TAKER_FEE = Decimal('0.00025')




import os

from dotenv import load_dotenv
load_dotenv()


HYPERLIQUID_SECRET_KEY = os.getenv('HYPERLIQUID_SECRET_KEY')
HYPERLIQUID_ACCOUNT_ADDRESS = os.getenv('HYPERLIQUID_ACCOUNT_ADDRESS')



"""Load .env before pytest collects tests (so skipif sees API keys)."""

from dotenv import load_dotenv

load_dotenv()

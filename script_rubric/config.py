from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PARSED_DIR = DATA_DIR / "parsed"
OUTPUT_DIR = BASE_DIR / "outputs"
ARCHIVES_DIR = OUTPUT_DIR / "archives"
HANDBOOK_DIR = OUTPUT_DIR / "handbook"
BACKTEST_DIR = OUTPUT_DIR / "backtest"
PROMPT_DIR = BASE_DIR / "prompts"

XLSX_PATH = PROJECT_ROOT / "uploads" / "外部待审核剧本.xlsx"
DRAMA_DIR = PROJECT_ROOT / "uploads" / "drama"

API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://yibuapi.com/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("RUBRIC_MODEL") or os.getenv("OPENAI_MODEL") or "claude-sonnet-4-6-20250514"

PASS1_CONCURRENCY = 5
PASS1_MAX_RETRIES = 2
HOLDOUT_RATIO = 0.2
HOLDOUT_SEED = 42
MAX_ITERATE_ROUNDS = 3

BACKTEST_STATUS_ACCURACY = 0.70
BACKTEST_RANGE_ACCURACY = 0.60
BACKTEST_MAE_THRESHOLD = 8
BACKTEST_CRITICAL_MISS_RATE = 0.10

MIN_SCORES_FOR_INCLUSION = 3
SCORE_TIER_THRESHOLDS = {"签": 80, "改": 70}  # >=80 签, >=70 改, <70 拒

XLSX_COLUMNS = {
    "source_type": 0,
    "genre": 1,
    "title": 2,
    "submitter": 3,
    "status": 4,
    "overall_score": 5,
}

REVIEWERS = [
    ("小冉", 6, 7),
    ("贾酒", 8, 9),
    ("47", 10, 11),
    ("宇间", 12, 13),
    ("帕克", 14, 15),
    ("Vicki", 16, 17),
    ("千北", 18, 19),
    ("小刚", 20, 21),
    ("山南", 22, 23),
    ("安兔兔", 24, 25),
    ("步步", 26, 27),
]

DIMENSION_KEYS = [
    "premise_innovation",
    "opening_hook",
    "character_depth",
    "pacing_conflict",
    "writing_dialogue",
    "payoff_satisfaction",
    "benchmark_differentiation",
]

DIMENSION_NAMES_ZH = {
    "premise_innovation": "题材与设定创新度",
    "opening_hook": "开局与钩子",
    "character_depth": "人设立体度",
    "pacing_conflict": "节奏与冲突密度",
    "writing_dialogue": "文笔与台词",
    "payoff_satisfaction": "爽点兑现",
    "benchmark_differentiation": "对标与差异化",
}

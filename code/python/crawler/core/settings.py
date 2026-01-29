"""
settings.py - 爬蟲設定模組

集中管理爬蟲相關設定，支援從 config/config_crawler.yaml 讀取。
"""

import os
from pathlib import Path
import logging

# ==================== 專案目錄設定 ====================
# 以 nlweb 專案根目錄為基準
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent  # nlweb/
CODE_DIR = BASE_DIR / "code" / "python" / "crawler"

# 定義資料與日誌目錄
DATA_DIR = BASE_DIR / "data" / "crawler"
LOG_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "articles"
CRAWLED_IDS_DIR = DATA_DIR / "crawled_ids"

# 確保目錄存在
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CRAWLED_IDS_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 日誌設定 ====================
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# ==================== HTTP 請求設定 ====================
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2

# SSL 驗證設定
# 生產環境建議設為 True，開發/測試環境可設為 False
SSL_VERIFY = os.environ.get("CRAWLER_SSL_VERIFY", "true").lower() in ("true", "1", "yes")

# SSL 憑證路徑（可選，用於自訂 CA 憑證）
SSL_CA_BUNDLE = os.environ.get("CRAWLER_SSL_CA_BUNDLE", None)

# 重試延遲設定
RETRY_DELAY = 3.0
MAX_RETRY_DELAY = 60

# 併發控制
CONCURRENT_REQUESTS = 3
MIN_DELAY = 0.8
MAX_DELAY = 2.9

# 429 降速設定
RATE_LIMIT_COOLDOWN = 10.0
RATE_LIMIT_BACKOFF = 2.0

# 封鎖冷卻設定
BLOCKED_COOLDOWN = 20.0

# ==================== 預設 HTTP Headers ====================
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"macOS"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
}

# ==================== User-Agent 池 ====================
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# ==================== Session 類型設定 ====================
# 需要 curl_cffi 繞過反爬蟲的來源
CURL_CFFI_SOURCES = [
    'cna',
    'chinatimes',
    'einfo',
    'esg_businesstoday',
]

# ==================== 新聞來源設定 ====================
NEWS_SOURCES = {
    "ltn": {
        "name": "自由時報",
        "concurrent_limit": 5,
        "delay_range": (0.5, 1.5),
    },
    "udn": {
        "name": "聯合報",
        "concurrent_limit": 5,
        "delay_range": (0.5, 1.5),
    },
    "cna": {
        "name": "中央社",
        "concurrent_limit": 3,
        "delay_range": (1.0, 2.5),
    },
    "moea": {
        "name": "經濟部",
        "concurrent_limit": 5,
        "delay_range": (1.0, 2.5),
    },
    "einfo": {
        "name": "環境資訊中心",
        "concurrent_limit": 1,
        "delay_range": (5.0, 10.0),
    },
    "esg_businesstoday": {
        "name": "今周刊 ESG",
        "concurrent_limit": 2,
        "delay_range": (1.5, 3.5),
    },
}

# ==================== 輸出設定 ====================
OUTPUT_FORMAT = "tsv"
ENSURE_ASCII = True
MAX_ARTICLE_LENGTH = 20000

# ==================== 爬取模式設定 ====================
DEFAULT_MODE = "date"
DEFAULT_MAX_ARTICLES = 300
DEFAULT_DAYS_BACK = 3

# 停止條件
CONSECUTIVE_TOO_OLD_LIMIT = 30
CONSECUTIVE_FAIL_LIMIT = 50
MAX_CONSECUTIVE_MISSES = 100

# 智能跳躍設定
SMART_JUMP_THRESHOLD = 100
SMART_JUMP_ENABLED_SOURCES = ['chinatimes', 'cna']

# ==================== 調試設定 ====================
DEBUG = os.environ.get("NLWEB_DEBUG", "").lower() in ("true", "1", "yes")

# ==================== Schema.org 設定 ====================
SCHEMA_CONFIG = {
    'context': 'https://schema.org',
    'type': 'NewsArticle',
    'max_body_length': MAX_ARTICLE_LENGTH,
    'required_fields': [
        'headline',
        'datePublished',
        'articleBody',
        '@type',
        '@context'
    ]
}

# ==================== Parser 專用設定 ====================
# UDN Parser
UDN_DEFAULT_CATEGORY = "6656"
UDN_COMMON_CATEGORIES = [
    "6656",  # 政治
    "7088",  # 生活
    "7314",  # 社會
    "6809",  # 全球
    "7238",  # 地方
    "7239",  # 兩岸
    "6885",  # 產經
]

# LTN Parser
LTN_MAIN_CATEGORIES = [
    'life', 'politics', 'society', 'world',
    'business', 'entertainment', 'sports'
]

# ESG BusinessToday Parser
ESG_BT_CATEGORIES = {
    180686: "全部",
    180687: "E永續環境",
    180688: "S社會責任",
    180689: "G公司治理",
    190807: "ESG快訊"
}

# EInfo Parser
EINFO_CATEGORY_URLS = [
    "https://e-info.org.tw/taxonomy/term/258/all",
    "https://e-info.org.tw/taxonomy/term/266",
    "https://e-info.org.tw/taxonomy/term/35283/all"
]
EINFO_DEFAULT_LATEST_ID = 242797

# 通用文本處理
MIN_PARAGRAPH_LENGTH = 20
MIN_ARTICLE_LENGTH = 50
MAX_KEYWORDS = 10

# 停用詞（用於簡易關鍵字提取）
STOPWORDS_ZH = {
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
    '都', '一', '一個', '上', '也', '很', '到', '說', '要', '去',
    '你', '會', '著', '沒有', '看', '好', '自己', '這'
}

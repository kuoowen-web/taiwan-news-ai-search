"""
interfaces.py - Parser 介面定義

定義所有新聞網站 Parser 必須實作的標準合約。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
import logging


class SessionType(Enum):
    """
    Session 類型列舉

    用途：指定 Parser 偏好的 HTTP Session 類型
    - AIOHTTP: 標準的 aiohttp.ClientSession（適用於大部分網站）
    - CURL_CFFI: curl_cffi.AsyncSession（適用於反爬強的網站，如 CNA）
    """
    AIOHTTP = "aiohttp"
    CURL_CFFI = "curl_cffi"


class BaseParser(ABC):
    """
    Parser 基底介面
    定義所有新聞網站 Parser 必須實作的標準合約

    設計原則：
    1. 只定義介面，不包含實作邏輯
    2. 讓爬蟲引擎只依賴此介面，不依賴具體網站
    3. 所有具體的 Parser 必須繼承此類別並實作所有抽象方法
    """

    # 子類別可以覆寫此屬性來指定偏好的 Session 類型
    preferred_session_type: Optional[SessionType] = None

    def __init__(self):
        """
        初始化 Parser

        自動設定 logger，使用類別名稱作為 logger 名稱。
        子類別應呼叫 super().__init__() 來繼承此行為。
        """
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        回傳新聞來源代號

        Returns:
            來源代號，如 'ltn', 'udn', 'cna' 等

        範例:
            >>> parser.source_name
            'ltn'
        """
        pass

    @abstractmethod
    def get_url(self, article_id: int) -> str:
        """
        將文章 ID 轉換為完整的文章 URL

        Args:
            article_id: 文章 ID（整數）

        Returns:
            完整的文章 URL

        範例:
            >>> parser.get_url(4567890)
            'https://news.ltn.com.tw/news/life/breakingnews/4567890'
        """
        pass

    @abstractmethod
    async def get_latest_id(self, session=None) -> Optional[int]:
        """
        取得該網站目前最新的文章 ID

        用途：
        1. 確定爬取範圍的上界
        2. 用於增量更新（只爬取新文章）

        Args:
            session: HTTP Session 實例（可選）

        Returns:
            最新的文章 ID，或 None（如果獲取失敗）

        範例:
            >>> await parser.get_latest_id(session)
            4567890
        """
        pass

    @abstractmethod
    async def parse(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """
        解析文章 HTML，提取結構化資料

        要求：
        1. 回傳的字典必須符合 Schema.org NewsArticle 格式
        2. 必須包含必要欄位：headline, datePublished, articleBody
        3. 如果內文過短（< 100 字）或無效，必須回傳 None
        4. 必須包含 HTML 特徵（用於後續分析）

        Args:
            html: 文章的 HTML 內容
            url: 文章的 URL

        Returns:
            符合 Schema.org NewsArticle 格式的字典，或 None（如果解析失敗或內容無效）

        回傳格式範例:
            {
                '@context': 'https://schema.org',
                '@type': 'NewsArticle',
                'headline': '文章標題',
                'datePublished': '2025-12-08T10:30:00',
                'dateModified': '2025-12-08T11:00:00',  # 可選
                'author': {
                    '@type': 'Person',
                    'name': '記者姓名'
                },
                'articleBody': '文章內容...',
                'url': 'https://...',
                'publisher': {
                    '@type': 'Organization',
                    'name': '自由時報'
                },
                '_html_features': {  # 自訂欄位，用於分析
                    'link_count': 10,
                    'image_count': 3,
                    'paragraph_count': 15,
                    'word_count': 500
                }
            }
        """
        pass

    @abstractmethod
    async def get_date(self, article_id: int) -> Optional[datetime]:
        """
        取得指定文章 ID 的發布日期

        用途：
        1. 供 Navigator 使用，進行二分搜尋
        2. 快速檢查文章是否存在
        3. 不需要完整解析文章，只提取日期即可

        Args:
            article_id: 文章 ID

        Returns:
            文章發布日期（datetime 物件），或 None（如果文章不存在或獲取失敗）

        範例:
            >>> await parser.get_date(4567890)
            datetime(2025, 12, 8, 10, 30, 0)

        注意：
        1. 此方法應該輕量化，避免完整解析 HTML
        2. 只需要提取日期資訊即可
        3. 如果文章不存在（404），應返回 None
        """
        pass



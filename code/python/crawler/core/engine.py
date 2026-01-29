"""
engine.py - 通用爬蟲引擎

核心爬蟲引擎，負責：
- 範圍爬取：run_range(start_id, end_id)
- 列表爬取：run_list(url_list)
- 自動爬取：run_auto(count)
- 併發控制、重試機制、去重機制
"""

import asyncio
import aiohttp
import logging
import random
import time
from typing import Dict, List, Optional, Any, Set, Union
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum

from . import settings
from .settings import DEFAULT_HEADERS
from .interfaces import BaseParser, SessionType
from .pipeline import Pipeline

# 嘗試引入 curl_cffi
try:
    from curl_cffi.requests import AsyncSession as CurlSession
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    CurlSession = None


class CrawlStatus(Enum):
    """爬取狀態列舉"""
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"


class CrawlerEngine:
    """
    通用爬蟲引擎

    設計原則：
    1. 依賴注入：透過 BaseParser 介面與具體網站解耦
    2. 關注點分離：只負責爬取流程，解析邏輯委託給 Parser
    3. 可重用：適用於所有實作 BaseParser 的網站
    """

    SMART_JUMP_THRESHOLD = 100

    def __init__(
        self,
        parser: BaseParser,
        session: Optional[Union[aiohttp.ClientSession, 'CurlSession']] = None,
        auto_save: bool = True
    ):
        """
        初始化爬蟲引擎

        Args:
            parser: BaseParser 實例（必須）
            session: HTTP Session 實例（可選）
            auto_save: 是否自動儲存爬取結果（預設 True）
        """
        self.parser = parser
        self.session = session
        self.auto_save = auto_save

        # 載入來源專屬設定
        self._load_source_config()

        # 判斷 Session 類型
        if session is not None:
            if CURL_CFFI_AVAILABLE and isinstance(session, CurlSession):
                self.session_type = SessionType.CURL_CFFI
            else:
                self.session_type = SessionType.AIOHTTP
        else:
            if parser.source_name in settings.CURL_CFFI_SOURCES:
                self.session_type = SessionType.CURL_CFFI
            else:
                self.session_type = SessionType.AIOHTTP

        # 設定日誌
        self.logger = logging.getLogger(f"CrawlerEngine_{parser.source_name}")
        self._setup_logger()

        self.logger.info(f"Engine initialized with session type: {self.session_type.value}")
        self.logger.info(f"   Concurrent limit: {self.concurrent_limit}")
        self.logger.info(f"   Delay range: {self.min_delay:.1f}s - {self.max_delay:.1f}s")

        # 初始化 Pipeline
        if self.auto_save:
            self.pipeline = Pipeline(source_name=parser.source_name)

        # 載入歷史記錄（去重）
        self.crawled_ids: Set[str] = set()
        self._load_history()

        # 統計資訊
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'not_found': 0,
            'blocked': 0,
        }

        # 智能跳躍狀態
        self.consecutive_failures = 0
        self.smart_jump_count = 0

        # 429 降速狀態
        self.rate_limit_hit = False
        self.rate_limit_cooldown_until = 0

    def _load_source_config(self) -> None:
        """載入來源專屬設定"""
        source_name = self.parser.source_name

        if source_name in settings.NEWS_SOURCES:
            source_config = settings.NEWS_SOURCES[source_name]
            self.concurrent_limit = source_config.get(
                'concurrent_limit', settings.CONCURRENT_REQUESTS
            )
            delay_range = source_config.get(
                'delay_range', (settings.MIN_DELAY, settings.MAX_DELAY)
            )
            self.min_delay, self.max_delay = delay_range
        else:
            self.concurrent_limit = settings.CONCURRENT_REQUESTS
            self.min_delay = settings.MIN_DELAY
            self.max_delay = settings.MAX_DELAY

    def _setup_logger(self) -> None:
        """設置日誌處理器"""
        if self.logger.handlers:
            return

        settings.LOG_DIR.mkdir(parents=True, exist_ok=True)

        log_file = settings.LOG_DIR / f"engine_{self.parser.source_name}_{time.strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        console_handler = logging.StreamHandler()

        formatter = logging.Formatter(
            settings.LOG_FORMAT,
            datefmt=settings.LOG_DATE_FORMAT
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(settings.LOG_LEVEL)

    def _load_history(self) -> int:
        """載入歷史已爬取的 URL 記錄"""
        try:
            ids_file = settings.CRAWLED_IDS_DIR / f"{self.parser.source_name}.txt"

            if not ids_file.exists():
                self.logger.info(f"No history file found, starting fresh")
                return 0

            with open(ids_file, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url:
                        self.crawled_ids.add(url)

            count = len(self.crawled_ids)
            self.logger.info(f"Loaded {count:,} crawled URLs from history")
            return count

        except Exception as e:
            self.logger.error(f"Error loading history: {str(e)}")
            return 0

    def _is_crawled(self, url: str) -> bool:
        """檢查 URL 是否已爬取"""
        return url in self.crawled_ids

    def _mark_as_crawled(self, url: str) -> None:
        """標記 URL 為已爬取"""
        self.crawled_ids.add(url)

    async def _create_session(self) -> Union[aiohttp.ClientSession, 'CurlSession']:
        """創建 Session"""
        if self.session_type == SessionType.CURL_CFFI:
            if not CURL_CFFI_AVAILABLE:
                self.logger.warning("curl_cffi not available, falling back to aiohttp")
                self.session_type = SessionType.AIOHTTP
            else:
                self.logger.info("Creating curl_cffi session")
                return CurlSession(
                    headers=DEFAULT_HEADERS,
                    timeout=settings.REQUEST_TIMEOUT,
                    impersonate="chrome110"
                )

        self.logger.info("Creating aiohttp session")
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        return aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT),
            headers=DEFAULT_HEADERS
        )

    def _get_headers(self) -> Dict[str, str]:
        """獲取請求標頭（支援動態 User-Agent 輪換）"""
        headers = DEFAULT_HEADERS.copy()
        headers['User-Agent'] = random.choice(settings.USER_AGENTS)
        return headers

    async def _handle_rate_limit(self) -> None:
        """處理 429 Rate Limit 錯誤"""
        self.rate_limit_hit = True
        cooldown = settings.RATE_LIMIT_COOLDOWN

        self.logger.warning(f"Rate limit detected (429), cooling down for {cooldown}s...")
        self.rate_limit_cooldown_until = time.time() + cooldown

        await asyncio.sleep(cooldown)

        self.rate_limit_hit = False
        self.logger.info(f"Cooldown completed, resuming...")

    async def _fetch(
        self,
        url: str,
        session: Union[aiohttp.ClientSession, 'CurlSession']
    ) -> tuple[Optional[str], CrawlStatus]:
        """獲取 URL 內容，包含重試機制"""
        if self.rate_limit_hit:
            wait_time = self.rate_limit_cooldown_until - time.time()
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        retry_count = 0
        max_retries = settings.MAX_RETRIES

        while retry_count <= max_retries:
            try:
                headers = self._get_headers()

                if self.session_type == SessionType.CURL_CFFI:
                    response = await session.get(url, headers=headers)
                    status = response.status_code

                    if status == 200:
                        return (response.text, CrawlStatus.SUCCESS)
                    elif status == 404:
                        return (None, CrawlStatus.NOT_FOUND)
                    elif status in (403, 429):
                        await self._handle_rate_limit()
                    elif status in (500, 502, 503, 504):
                        pass  # 繼續重試
                    else:
                        return (None, CrawlStatus.BLOCKED)
                else:
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)
                    ) as response:
                        if response.status == 200:
                            return (await response.text(), CrawlStatus.SUCCESS)
                        elif response.status == 404:
                            return (None, CrawlStatus.NOT_FOUND)
                        elif response.status in (403, 429):
                            await self._handle_rate_limit()
                        elif response.status in (500, 502, 503, 504):
                            pass  # 繼續重試
                        else:
                            return (None, CrawlStatus.BLOCKED)

            except asyncio.TimeoutError:
                self.logger.debug(f"Timeout for {url}")
                return (None, CrawlStatus.NOT_FOUND)

            except Exception as e:
                self.logger.debug(f"Network error fetching {url}: {str(e)}")

            retry_count += 1
            if retry_count <= max_retries:
                wait_time = settings.RETRY_DELAY * (2 ** (retry_count - 1))
                await asyncio.sleep(min(wait_time, settings.MAX_RETRY_DELAY))

        return (None, CrawlStatus.BLOCKED)

    async def _random_delay(self):
        """隨機延遲"""
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

    async def _process_article(
        self,
        article_id: int,
        session: Union[aiohttp.ClientSession, 'CurlSession']
    ) -> CrawlStatus:
        """處理單篇文章"""
        url = self.parser.get_url(article_id)

        if not url:
            self.stats['not_found'] += 1
            return CrawlStatus.NOT_FOUND

        if self._is_crawled(url):
            self.stats['skipped'] += 1
            return CrawlStatus.SUCCESS

        html, status = await self._fetch(url, session)

        if status == CrawlStatus.NOT_FOUND:
            self.stats['not_found'] += 1
            return CrawlStatus.NOT_FOUND

        if status == CrawlStatus.BLOCKED:
            self.stats['blocked'] += 1
            return CrawlStatus.BLOCKED

        if html is None:
            self.stats['failed'] += 1
            return CrawlStatus.BLOCKED

        try:
            data = await self.parser.parse(html, url)
            if data is None:
                self.stats['failed'] += 1
                return CrawlStatus.NOT_FOUND

            self._mark_as_crawled(url)

            if self.auto_save:
                success = await self.pipeline.process_and_save(url, data)
                if success:
                    self.logger.info(f"Parsed ID: {article_id:,}")
                    self.stats['success'] += 1
                else:
                    self.stats['failed'] += 1
            else:
                self.logger.info(f"Parsed ID: {article_id:,}")
                self.stats['success'] += 1

            return CrawlStatus.SUCCESS

        except Exception as e:
            self.logger.error(f"Error parsing {url}: {str(e)}")
            self.stats['failed'] += 1
            return CrawlStatus.BLOCKED

    async def run_auto(self, count: int = 100) -> Dict[str, Any]:
        """
        自動爬取最新文章

        Args:
            count: 要爬取的文章數量

        Returns:
            爬取結果統計
        """
        self.logger.info(f"Starting auto crawl: {count} articles")

        # 創建會話（提前建立以供 get_latest_id 使用）
        need_close = self.session is None
        if need_close:
            self.session = await self._create_session()

        latest_id = await self.parser.get_latest_id(session=self.session)
        if latest_id is None:
            self.logger.error("Failed to get latest ID")
            if need_close:
                await self.close()
            return {'error': 'Failed to get latest ID'}

        self.logger.info(f"Latest ID: {latest_id:,}")

        # Duck Typing: 檢查是否支援列表式爬取
        if hasattr(self.parser, 'get_discovered_ids') and callable(getattr(self.parser, 'get_discovered_ids')):
            self.logger.info("List-based parser detected")
            valid_ids = self.parser.get_discovered_ids()

            if valid_ids:
                target_ids = valid_ids[:count]
                self.logger.info(f"Using {len(target_ids)} discovered IDs")
            else:
                target_ids = list(range(latest_id, latest_id - count, -1))
        else:
            target_ids = list(range(latest_id, latest_id - count, -1))
            self.logger.info(f"Range-based crawling: {latest_id:,} -> {latest_id - count:,}")

        # 重置統計
        self.stats = {
            'total': len(target_ids),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'not_found': 0,
            'blocked': 0,
        }

        semaphore = asyncio.Semaphore(self.concurrent_limit)

        async def process_with_semaphore(article_id: int):
            async with semaphore:
                await self._random_delay()
                return await self._process_article(article_id, self.session)

        tasks = [process_with_semaphore(aid) for aid in target_ids]
        self.logger.info(f"Processing {len(tasks)} articles with {self.concurrent_limit} concurrent requests")

        await asyncio.gather(*tasks, return_exceptions=True)

        if need_close:
            await self.close()

        self._log_stats()
        return self.stats

    async def run_range(
        self,
        start_id: int,
        end_id: int,
        reverse: bool = False
    ) -> Dict[str, Any]:
        """
        爬取指定範圍的文章 ID

        Args:
            start_id: 起始 ID
            end_id: 結束 ID
            reverse: 是否反向爬取

        Returns:
            爬取結果統計
        """
        if not reverse and start_id > end_id:
            start_id, end_id = end_id, start_id
        elif reverse and start_id < end_id:
            start_id, end_id = end_id, start_id

        step = -1 if reverse else 1
        direction = "reverse" if reverse else "forward"

        self.logger.info(f"Starting crawl: ID {start_id:,} -> {end_id:,} ({direction})")

        total_range = abs(start_id - end_id) + 1
        self.stats = {
            'total': total_range,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'not_found': 0,
            'blocked': 0,
        }

        need_close = self.session is None
        if need_close:
            self.session = await self._create_session()

        semaphore = asyncio.Semaphore(self.concurrent_limit)

        async def process_with_semaphore(article_id: int):
            async with semaphore:
                await self._random_delay()
                return await self._process_article(article_id, self.session)

        target_ids = list(range(start_id, end_id + step, step))
        tasks = [process_with_semaphore(aid) for aid in target_ids]

        self.logger.info(f"Processing {len(tasks)} articles")
        await asyncio.gather(*tasks, return_exceptions=True)

        if need_close:
            await self.close()

        self._log_stats()
        return self.stats

    def _log_stats(self) -> None:
        """輸出統計資訊"""
        self.logger.info("=" * 50)
        self.logger.info("Crawl Statistics:")
        self.logger.info(f"  Total:     {self.stats['total']}")
        self.logger.info(f"  Success:   {self.stats['success']}")
        self.logger.info(f"  Failed:    {self.stats['failed']}")
        self.logger.info(f"  Skipped:   {self.stats['skipped']}")
        self.logger.info(f"  Not Found: {self.stats['not_found']}")
        self.logger.info(f"  Blocked:   {self.stats['blocked']}")

        if self.stats['total'] > 0:
            rate = (self.stats['success'] / self.stats['total']) * 100
            self.logger.info(f"  Success Rate: {rate:.1f}%")

        self.logger.info("=" * 50)

    async def close(self) -> None:
        """關閉 Session"""
        if self.session is not None:
            try:
                if self.session_type == SessionType.AIOHTTP:
                    await asyncio.wait_for(self.session.close(), timeout=5.0)
                else:
                    self.session.close()
                self.logger.info("Session closed")
            except asyncio.TimeoutError:
                self.logger.warning("Session close timed out")
            except Exception as e:
                self.logger.warning(f"Error closing session: {e}")
            finally:
                self.session = None

"""크롤러 모듈"""

from .base_crawler import BaseCrawler
from .notice_crawler import NoticeCrawler
from .job_crawler import JobCrawler
from .seminar_crawler import SeminarCrawler
from .professor_crawler import ProfessorCrawler

__all__ = [
    'BaseCrawler',
    'NoticeCrawler',
    'JobCrawler',
    'SeminarCrawler',
    'ProfessorCrawler'
]

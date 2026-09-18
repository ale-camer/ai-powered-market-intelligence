"""Integration test for NewsAPIExtractor against live NewsAPI endpoint."""

import os

import pytest

from market_intel.extractors.newsapi import NewsAPIExtractor
from market_intel.extractors.schemas import ArticleSchema

NEWSAPI_KEY = os.getenv("NEWSAPI_API_KEY", "").strip()


@pytest.mark.integration
@pytest.mark.issue_2
@pytest.mark.issue_02
@pytest.mark.skipif(
    not NEWSAPI_KEY,
    reason="NEWSAPI_API_KEY not configured or empty; skipping live integration test",
)
async def test_newsapi_live_fetch() -> None:
    """Validate live API request and parsing against NewsAPI."""
    async with NewsAPIExtractor(api_key=NEWSAPI_KEY) as extractor:
        articles = await extractor.get_articles(
            query="technology",
            page_size=5,
            max_articles=5,
        )

        assert isinstance(articles, list)
        assert len(articles) > 0
        for article in articles:
            assert isinstance(article, ArticleSchema)
            assert article.title
            assert article.url

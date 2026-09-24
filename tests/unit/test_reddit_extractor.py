"""Unit tests for the RedditExtractor."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from prawcore.exceptions import OAuthException, PrawcoreException, ResponseException

from market_intel.core.exceptions import AuthenticationError, RedditError
from market_intel.extractors.reddit import RedditExtractor


@pytest.fixture
def mock_praw() -> Generator[MagicMock, None, None]:
    """Mock the praw.Reddit class."""
    with patch("market_intel.extractors.reddit.praw.Reddit") as mock_reddit:
        yield mock_reddit


@pytest.fixture
def extractor(mock_praw: MagicMock) -> RedditExtractor:
    """Return a RedditExtractor instance with mocked PRAW."""
    return RedditExtractor()


@pytest.mark.issue_4
def test_fetch_top_posts_success(extractor: RedditExtractor, mock_praw: MagicMock) -> None:
    """Test successful fetching and mapping of Reddit posts."""
    # Setup mock submission
    mock_submission = MagicMock()
    mock_submission.title = "Test Post"
    mock_submission.selftext = "This is a test post body."
    mock_submission.score = 100
    mock_submission.num_comments = 50
    mock_submission.created_utc = 1672531200.0  # 2023-01-01 00:00:00 UTC
    mock_submission.link_flair_text = "Discussion"

    mock_subreddit = MagicMock()
    mock_subreddit.top.return_value = [mock_submission]
    extractor.reddit.subreddit.return_value = mock_subreddit

    posts = extractor.fetch_top_posts(["wallstreetbets"], time_filter="day", limit=1)

    assert len(posts) == 1
    post = posts[0]
    assert post.subreddit == "wallstreetbets"
    assert post.title == "Test Post"
    assert post.body == "This is a test post body."
    assert post.score == 100
    assert post.num_comments == 50
    assert post.created_utc == datetime(2023, 1, 1, 0, 0, tzinfo=UTC)
    assert post.flair == "Discussion"


@pytest.mark.issue_4
def test_fetch_top_posts_missing_optional_fields(
    extractor: RedditExtractor, mock_praw: MagicMock
) -> None:
    """Test fetching posts that lack optional fields like selftext and flair."""
    # Setup mock submission with missing optional attributes
    mock_submission = MagicMock(spec=["title", "score", "num_comments", "created_utc"])
    mock_submission.title = "Link Post"
    mock_submission.score = 10
    mock_submission.num_comments = 5
    mock_submission.created_utc = 1672531200.0

    mock_subreddit = MagicMock()
    mock_subreddit.top.return_value = [mock_submission]
    extractor.reddit.subreddit.return_value = mock_subreddit

    posts = extractor.fetch_top_posts(["investing"], time_filter="day", limit=1)

    assert len(posts) == 1
    post = posts[0]
    assert post.body is None
    assert post.flair is None


@pytest.mark.issue_4
def test_oauth_exception_raises_auth_error(
    extractor: RedditExtractor, mock_praw: MagicMock
) -> None:
    """Test that OAuthException is mapped to AuthenticationError."""
    mock_subreddit = MagicMock()
    mock_subreddit.top.side_effect = OAuthException(None, None, None)
    extractor.reddit.subreddit.return_value = mock_subreddit

    with pytest.raises(AuthenticationError, match="Reddit OAuth authentication failed"):
        extractor.fetch_top_posts(["stocks"])


@pytest.mark.issue_4
def test_response_exception_401_raises_auth_error(
    extractor: RedditExtractor, mock_praw: MagicMock
) -> None:
    """Test that ResponseException with 401 is mapped to AuthenticationError."""
    mock_response = MagicMock()
    mock_response.status_code = 401

    mock_subreddit = MagicMock()
    mock_subreddit.top.side_effect = ResponseException(mock_response)
    extractor.reddit.subreddit.return_value = mock_subreddit

    with pytest.raises(AuthenticationError, match="Reddit authentication failed \\(401\\)"):
        extractor.fetch_top_posts(["stocks"])


@pytest.mark.issue_4
def test_other_prawcore_exception_raises_reddit_error(
    extractor: RedditExtractor, mock_praw: MagicMock
) -> None:
    """Test that a general PrawcoreException is mapped to RedditError."""
    mock_subreddit = MagicMock()
    mock_request = MagicMock()
    mock_subreddit.top.side_effect = PrawcoreException(mock_request)
    extractor.reddit.subreddit.return_value = mock_subreddit

    with pytest.raises(RedditError, match="Error fetching from Reddit"):
        extractor.fetch_top_posts(["stocks"])

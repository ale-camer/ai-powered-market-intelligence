"""Extractor for fetching Reddit posts from financial subreddits."""

from datetime import UTC, datetime

import praw
from prawcore.exceptions import OAuthException, PrawcoreException, ResponseException

from market_intel.core.config import get_settings
from market_intel.core.exceptions import AuthenticationError, RedditError
from market_intel.extractors.schemas import PostSchema


class RedditExtractor:
    """Client for extracting data from Reddit using PRAW."""

    def __init__(self) -> None:
        """Initialize the PRAW Reddit client using settings from config."""
        settings = get_settings()
        self.reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    def fetch_top_posts(
        self, subreddits: list[str], time_filter: str = "day", limit: int = 10
    ) -> list[PostSchema]:
        """Fetch top posts from the specified subreddits.

        Args:
            subreddits: List of subreddit names (e.g., ['wallstreetbets', 'investing']).
            time_filter: The time filter for top posts (e.g., 'day', 'week', 'all').
            limit: Maximum number of posts to fetch per subreddit.

        Returns:
            A list of PostSchema objects representing the fetched posts.

        Raises:
            AuthenticationError: If OAuth authentication fails.
            RedditError: For other PRAW related errors.
        """
        posts = []
        try:
            for sub in subreddits:
                subreddit = self.reddit.subreddit(sub)
                for submission in subreddit.top(time_filter=time_filter, limit=limit):
                    post = PostSchema(
                        subreddit=sub,
                        title=submission.title,
                        body=getattr(submission, "selftext", None),
                        score=submission.score,
                        num_comments=submission.num_comments,
                        created_utc=datetime.fromtimestamp(submission.created_utc, tz=UTC),
                        flair=getattr(submission, "link_flair_text", None),
                    )
                    posts.append(post)
        except OAuthException as e:
            raise AuthenticationError("Reddit OAuth authentication failed.") from e
        except ResponseException as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Reddit authentication failed (401).") from e
            raise RedditError(f"Reddit API returned error: {e}") from e
        except PrawcoreException as e:
            raise RedditError(f"Error fetching from Reddit: {e}") from e

        return posts

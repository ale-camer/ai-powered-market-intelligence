# Issue 4: Implement Reddit PRAW extractor for financial subreddits

**Branch:** `feature/issue-4-reddit-extractor`  
**Status:** In Progress  
**PR:** TBD  

---

## Objective

Build `src/market_intel/extractors/reddit.py` using PRAW to scrape `r/wallstreetbets`, `r/investing`, and `r/stocks`.

---

## Acceptance Criteria

- [ ] **OAuth2 Authentication**: Authenticate via PRAW client using OAuth credentials.
- [ ] **Configuration**: Configurable subreddit list and time filter (day/week/month).
- [ ] **Data Extraction**: Extract title, body, score, num_comments, created_utc, and flair.
- [ ] **Pydantic Schemas**: Return a typed list of `PostSchema` Pydantic models.
- [ ] **Unit Tests**: Unit tests with mocked PRAW responses (`pytest -m issue_4`).

---

## Implementation Tasks

### 1. Preparation and Branching
```bash
make start-issue ID=4 NAME=reddit-extractor
```

### 2. Core Dependencies & Configuration
- **File**: `pyproject.toml`
  - Add `praw` to the `ingestion` optional dependencies group.
- **File**: `src/market_intel/core/config.py`
  - Add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` to the `Settings` class to support authentication.

### 3. Data Models & Schemas
- **File**: `src/market_intel/extractors/schemas.py`
  - Define `PostSchema` with fields: `title` (str), `body` (str | None), `score` (int), `num_comments` (int), `created_utc` (datetime), `flair` (str | None), and `subreddit` (str).

### 4. Extractor Implementation
- **File**: `src/market_intel/extractors/reddit.py`
  - Implement `RedditExtractor` class.
  - Initialize `praw.Reddit` client using credentials from `config.py`.
  - Implement `fetch_top_posts(subreddits: list[str], time_filter: str)` mapping PRAW `Submission` objects to `PostSchema`.
- **File**: `src/market_intel/extractors/__init__.py`
  - Re-export `RedditExtractor` and `PostSchema`.

### 5. Test Suite
- **File**: `tests/unit/test_reddit_extractor.py`
  - Create unit tests using `unittest.mock` to mock `praw.Reddit` interactions.
  - Test successful extraction and schema mapping.
  - Test authentication errors and empty body/flair scenarios.

### 6. Verification
```bash
make test-issue ID=4
make check
```

### 7. Completion & PR
```bash
make finish-issue ID=4
```

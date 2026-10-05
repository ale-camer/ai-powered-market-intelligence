"""Unit tests for the financial sentiment analysis pipeline."""

import json
from collections.abc import Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest

from market_intel.core.schemas import SentimentResult
from market_intel.transformers.sentiment import SentimentAnalyzer


class MockFinBERTModel:
    """Mock PyTorch/Transformers FinBERT model for deterministic fast unit testing."""

    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[list[str]] = []

    def predict_batch(self, texts: Sequence[str]) -> list[dict[str, Any]]:
        self.calls.append(list(texts))
        if self.responses:
            return self.responses[: len(texts)]
        return [
            {
                "label": "neutral",
                "score": 0.0,
                "confidence": 0.95,
                "probs": {"positive": 0.02, "negative": 0.03, "neutral": 0.95},
            }
            for _ in texts
        ]


class MockOpenAIClient:
    """Mock OpenAI API client for deterministic GPT-4o fallback testing."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        should_fail: bool = False,
    ) -> None:
        self.payload = payload or {
            "label": "positive",
            "score": 0.85,
            "confidence": 0.92,
            "explanation": "Clear guidance and revenue beat denote strong upside.",
        }
        self.should_fail = should_fail
        self.call_count = 0

    @property
    def chat(self) -> "MockOpenAIClient":
        return self

    @property
    def completions(self) -> "MockOpenAIClient":
        return self

    def create(self, **kwargs: object) -> object:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Simulated OpenAI rate limit or connection error")

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(self.payload)
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp


@pytest.mark.unit
@pytest.mark.issue_10
def test_finbert_positive_sentiment() -> None:
    """Verify high-confidence positive text is classified via FinBERT without fallback."""
    long_positive_text = (
        "Alphabet reported blowout fourth quarter earnings, surging cloud revenue by 35% "
        "and expanding operating margins across all key business divisions."
    )
    mock_model = MockFinBERTModel(
        [
            {
                "label": "positive",
                "score": 0.88,
                "confidence": 0.94,
                "probs": {"positive": 0.94, "negative": 0.06, "neutral": 0.00},
            }
        ]
    )
    mock_openai = MockOpenAIClient()

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
    )

    result = analyzer.analyze_text(long_positive_text)

    assert isinstance(result, SentimentResult)
    assert result.label == "positive"
    assert result.score == 0.88
    assert result.model_used == "ProsusAI/finbert"
    assert result.confidence == 0.94
    assert mock_openai.call_count == 0


@pytest.mark.unit
@pytest.mark.issue_10
def test_finbert_negative_sentiment() -> None:
    """Verify high-confidence negative text is classified via FinBERT without fallback."""
    long_negative_text = (
        "Boeing reported wider than expected quarterly losses as supply chain disruptions "
        "and manufacturing delays significantly reduced commercial aircraft deliveries."
    )
    mock_model = MockFinBERTModel(
        [
            {
                "label": "negative",
                "score": -0.82,
                "confidence": 0.91,
                "probs": {"positive": 0.04, "negative": 0.86, "neutral": 0.10},
            }
        ]
    )
    mock_openai = MockOpenAIClient()

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
    )

    result = analyzer.analyze_text(long_negative_text)

    assert result.label == "negative"
    assert result.score == -0.82
    assert result.model_used == "ProsusAI/finbert"
    assert mock_openai.call_count == 0


@pytest.mark.unit
@pytest.mark.issue_10
def test_finbert_neutral_sentiment() -> None:
    """Verify neutral financial announcement is classified properly."""
    long_neutral_text = (
        "The Federal Reserve announced the standard schedule for the upcoming "
        "Federal Open Market Committee policy meetings for the next calendar year."
    )
    mock_model = MockFinBERTModel(
        [
            {
                "label": "neutral",
                "score": 0.0,
                "confidence": 0.96,
                "probs": {"positive": 0.02, "negative": 0.02, "neutral": 0.96},
            }
        ]
    )
    mock_openai = MockOpenAIClient()

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
    )

    result = analyzer.analyze_text(long_neutral_text)

    assert result.label == "neutral"
    assert result.score == 0.0
    assert result.model_used == "ProsusAI/finbert"
    assert mock_openai.call_count == 0


@pytest.mark.unit
@pytest.mark.issue_10
def test_gpt4o_fallback_short_text() -> None:
    """Verify short headlines trigger GPT-4o fallback."""
    short_text = "Apple down 2%"  # 13 chars, < 5 words
    mock_model = MockFinBERTModel(
        [
            {
                "label": "negative",
                "score": -0.5,
                "confidence": 0.70,
                "probs": {"positive": 0.10, "negative": 0.60, "neutral": 0.30},
            }
        ]
    )
    mock_openai = MockOpenAIClient(
        payload={
            "label": "negative",
            "score": -0.40,
            "confidence": 0.88,
            "explanation": "Stock price drop of 2% indicates short-term selling pressure.",
        }
    )

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
        openai_model="gpt-4o",
    )

    result = analyzer.analyze_text(short_text)

    assert result.label == "negative"
    assert result.score == -0.40
    assert result.model_used == "gpt-4o"
    assert result.confidence == 0.88
    assert result.explanation is not None
    assert mock_openai.call_count == 1


@pytest.mark.unit
@pytest.mark.issue_10
def test_gpt4o_fallback_ambiguous_text() -> None:
    """Verify low confidence FinBERT output triggers GPT-4o fallback."""
    ambiguous_text = (
        "The company reported mixed results with higher revenue but compressed margins, "
        "leaving investors divided on the second half outlook."
    )
    mock_model = MockFinBERTModel(
        [
            {
                "label": "neutral",
                "score": 0.02,
                "confidence": 0.45,  # Low confidence below threshold 0.65
                "probs": {"positive": 0.28, "negative": 0.27, "neutral": 0.45},
            }
        ]
    )
    mock_openai = MockOpenAIClient(
        payload={
            "label": "neutral",
            "score": -0.05,
            "confidence": 0.80,
            "explanation": "Mixed indicators balance revenue upside against margin compression.",
        }
    )

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
        confidence_threshold=0.65,
    )

    result = analyzer.analyze_text(ambiguous_text)

    assert result.model_used == "gpt-4o"
    assert result.confidence == 0.80
    assert mock_openai.call_count == 1


@pytest.mark.unit
@pytest.mark.issue_10
def test_batch_processing_chunking() -> None:
    """Verify batch inference chunks inputs according to batch_size and preserves order."""
    texts = [
        "Company A revenue surged by 30% year over year in the second quarter.",
        "Company B missed earnings estimates and slashed future sales projections.",
        "Company C held its annual shareholder meeting without significant policy updates.",
        "Company D acquired a regional competitor to expand its market presence.",
        "Company E CEO announced immediate retirement amidst regulatory investigation.",
    ]

    mock_model = MockFinBERTModel()
    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        batch_size=2,
    )

    results = analyzer.analyze_batch(texts, batch_size=2)

    assert len(results) == 5
    # Batch size 2 means 3 chunks: [2, 2, 1]
    assert len(mock_model.calls) == 3
    assert len(mock_model.calls[0]) == 2
    assert len(mock_model.calls[1]) == 2
    assert len(mock_model.calls[2]) == 1


@pytest.mark.unit
@pytest.mark.issue_10
def test_empty_or_whitespace_handling() -> None:
    """Verify empty or whitespace strings return default neutral SentimentResult."""
    texts = ["", "   ", "Valid headline describing market operations and trade."]
    mock_model = MockFinBERTModel()

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
    )

    results = analyzer.analyze_batch(texts)

    assert len(results) == 3
    assert results[0].label == "neutral"
    assert results[0].score == 0.0
    assert results[1].label == "neutral"
    assert results[2].label == "neutral"
    # Only 1 non-empty text was sent to FinBERT
    assert len(mock_model.calls[0]) == 1


@pytest.mark.unit
@pytest.mark.issue_10
def test_openai_fallback_failure_resilience() -> None:
    """Verify pipeline gracefully falls back to FinBERT if OpenAI call raises an error."""
    short_text = "Tesla jumps 5%"
    mock_model = MockFinBERTModel(
        [
            {
                "label": "positive",
                "score": 0.65,
                "confidence": 0.70,
                "probs": {"positive": 0.70, "negative": 0.10, "neutral": 0.20},
            }
        ]
    )
    mock_openai = MockOpenAIClient(should_fail=True)

    analyzer = SentimentAnalyzer(
        model=mock_model,
        tokenizer=MagicMock(),
        openai_client=mock_openai,
    )

    result = analyzer.analyze_text(short_text)

    # Should fall back to FinBERT result instead of raising exception
    assert result.label == "positive"
    assert result.score == 0.65
    assert result.model_used == "ProsusAI/finbert"


@pytest.mark.unit
@pytest.mark.issue_10
def test_empty_batch_input() -> None:
    """Verify passing empty sequence returns empty list."""
    analyzer = SentimentAnalyzer(
        model=MockFinBERTModel(),
        tokenizer=MagicMock(),
    )
    assert analyzer.analyze_batch([]) == []


@pytest.mark.unit
@pytest.mark.issue_10
def test_lazy_loading_error_on_missing_model() -> None:
    """Verify RuntimeError is raised when neither model nor transformers dependencies exist."""
    analyzer = SentimentAnalyzer(finbert_model_name="non-existent/model-xyz")

    with pytest.raises(RuntimeError, match="FinBERT dependencies unavailable"):
        analyzer._get_model_and_tokenizer()


@pytest.mark.unit
@pytest.mark.issue_10
def test_openai_fallback_missing_client() -> None:
    """Verify fallback returns None if no OpenAI client is available."""
    analyzer = SentimentAnalyzer(model=MockFinBERTModel(), tokenizer=MagicMock())
    # Force client to None
    analyzer._openai_client = None
    res = analyzer._fallback_gpt4o("Short text")
    assert res is None


@pytest.mark.unit
@pytest.mark.issue_10
def test_openai_fallback_empty_content() -> None:
    """Verify fallback returns None if OpenAI returns empty content."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_client.chat.completions.create.return_value.choices = [mock_choice]

    analyzer = SentimentAnalyzer(
        model=MockFinBERTModel(),
        tokenizer=MagicMock(),
        openai_client=mock_client,
    )
    res = analyzer._fallback_gpt4o("Short text")
    assert res is None


@pytest.mark.unit
@pytest.mark.issue_10
def test_openai_fallback_invalid_label_normalized_to_neutral() -> None:
    """Verify fallback normalizes unrecognized labels to neutral."""
    mock_openai = MockOpenAIClient(
        payload={
            "label": "uncertain",
            "score": 0.1,
            "confidence": 0.5,
            "explanation": "Not sure.",
        }
    )
    analyzer = SentimentAnalyzer(
        model=MockFinBERTModel(),
        tokenizer=MagicMock(),
        openai_client=mock_openai,
    )
    res = analyzer._fallback_gpt4o("Short text")
    assert res is not None
    assert res.label == "neutral"


@pytest.mark.unit
@pytest.mark.issue_10
def test_get_openai_client_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify _get_openai_client returns None when OPENAI_API_KEY is empty."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from market_intel.core.config import get_settings

    get_settings.cache_clear()

    analyzer = SentimentAnalyzer()
    assert analyzer._get_openai_client() is None


@pytest.mark.unit
@pytest.mark.issue_19
def test_infer_finbert_batch_pytorch_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full PyTorch inference flow in _infer_finbert_batch with mocked torch."""
    import sys

    mock_torch = MagicMock()
    mock_torch.no_grad.return_value.__enter__ = MagicMock()
    mock_torch.no_grad.return_value.__exit__ = MagicMock()
    # Mock softmax output: positive=0.85, negative=0.05, neutral=0.10
    mock_torch.softmax.return_value.cpu.return_value.numpy.return_value = [[0.85, 0.05, 0.10]]
    monkeypatch.setitem(sys.modules, "torch", mock_torch)

    class FakeTorchModel:
        def __init__(self) -> None:
            self.config = MagicMock()
            self.config.id2label = {0: "positive", 1: "negative", 2: "neutral"}
            self._param = MagicMock()
            self._param.device = "cpu"

        def parameters(self) -> object:
            yield self._param

        def __call__(self, **kwargs: object) -> object:
            mock_out = MagicMock()
            mock_out.logits = MagicMock()
            return mock_out

    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {"input_ids": MagicMock()}

    analyzer = SentimentAnalyzer(model=FakeTorchModel(), tokenizer=mock_tokenizer)
    results = analyzer._infer_finbert_batch(["Record revenues and profit surge!"])

    assert len(results) == 1
    assert results[0]["label"] == "positive"
    assert results[0]["score"] == 0.8
    assert results[0]["confidence"] == 0.85


@pytest.mark.unit
@pytest.mark.issue_19
def test_get_model_and_tokenizer_lazy_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test lazy loading of model and tokenizer with GPU branch check."""
    import sys

    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    monkeypatch.setitem(sys.modules, "torch", mock_torch)

    mock_transformers = MagicMock()
    mock_auto_tokenizer = MagicMock()
    mock_auto_model = MagicMock()
    mock_transformers.AutoTokenizer = mock_auto_tokenizer
    mock_transformers.AutoModelForSequenceClassification = mock_auto_model

    mock_loaded_model = MagicMock()
    mock_auto_model.from_pretrained.return_value = mock_loaded_model
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    analyzer = SentimentAnalyzer()
    model, tokenizer = analyzer._get_model_and_tokenizer()

    assert model is mock_loaded_model
    mock_loaded_model.to.assert_called_with("cuda")


@pytest.mark.unit
@pytest.mark.issue_19
def test_get_openai_client_with_valid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify _get_openai_client successfully instantiates OpenAI client when key is set."""
    import sys

    mock_openai_module = MagicMock()
    mock_openai_cls = MagicMock()
    mock_openai_module.OpenAI = mock_openai_cls
    monkeypatch.setitem(sys.modules, "openai", mock_openai_module)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-valid-key-for-test")
    from market_intel.core.config import get_settings

    get_settings.cache_clear()

    analyzer = SentimentAnalyzer()
    client = analyzer._get_openai_client()
    assert client is not None
    mock_openai_cls.assert_called_once_with(api_key="sk-mock-valid-key-for-test")

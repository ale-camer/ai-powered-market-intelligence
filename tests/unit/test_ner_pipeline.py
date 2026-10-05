"""Unit tests for the financial Named Entity Recognition and sector tagging pipeline."""

from collections.abc import Callable, Sequence

import pytest

from market_intel.core.schemas import EntityItem, NERResult
from market_intel.transformers.ner import (
    FinancialNERExtractor,
    normalize_company_name,
)


class MockSpan:
    """Mock SpaCy entity Span."""

    def __init__(
        self,
        text: str,
        label: str,
        start_char: int = 0,
        end_char: int = 0,
    ) -> None:
        self.text = text
        self.label_ = label
        self.start_char = start_char
        self.end_char = end_char


class MockDoc:
    """Mock SpaCy Doc."""

    def __init__(self, text: str, ents: list[MockSpan] | None = None) -> None:
        self.text = text
        self.ents = ents or []


class MockSpaCyNLP:
    """Mock SpaCy Language model for deterministic unit testing."""

    def __init__(
        self,
        doc_factory: Callable[[str], MockDoc] | None = None,
    ) -> None:
        self.doc_factory = doc_factory
        self.calls: list[str] = []

    def __call__(self, text: str) -> MockDoc:
        self.calls.append(text)
        if self.doc_factory:
            return self.doc_factory(text)
        return MockDoc(text, [])

    def pipe(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
    ) -> list[MockDoc]:
        return [self(t) for t in texts]


@pytest.mark.unit
@pytest.mark.issue_11
def test_normalize_company_name() -> None:
    """Verify company name normalization strips corporate suffixes and punctuation."""
    assert normalize_company_name("Apple Inc.") == "apple"
    assert normalize_company_name("Microsoft Corporation") == "microsoft"
    assert normalize_company_name("The Boeing Company") == "the boeing"
    assert normalize_company_name("Alphabet, Inc.") == "alphabet"
    assert normalize_company_name("JPMorgan Chase & Co.") == "jpmorgan chase &"


@pytest.mark.unit
@pytest.mark.issue_11
def test_entity_extraction_targets() -> None:
    """Verify target entities (ORG, MONEY, PERCENT, DATE) are extracted into NERResult."""
    text = "Apple Inc. reported $25 billion in revenue, growing 15% in Q4 2026."

    def factory(t: str) -> MockDoc:
        return MockDoc(
            t,
            [
                MockSpan("Apple Inc.", "ORG", 0, 10),
                MockSpan("$25 billion", "MONEY", 20, 31),
                MockSpan("15%", "PERCENT", 52, 55),
                MockSpan("Q4 2026", "DATE", 59, 66),
                MockSpan("Tim Cook", "PERSON", 70, 78),  # Non-target entity, should be ignored
            ],
        )

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    result = extractor.extract_text(text)

    assert isinstance(result, NERResult)
    assert result.entities["ORG"] == ["Apple Inc."]
    assert result.entities["MONEY"] == ["$25 billion"]
    assert result.entities["PERCENT"] == ["15%"]
    assert result.entities["DATE"] == ["Q4 2026"]
    assert "PERSON" not in result.entities

    # Detailed entities
    assert len(result.detailed_entities) == 4
    first_ent = result.detailed_entities[0]
    assert isinstance(first_ent, EntityItem)
    assert first_ent.text == "Apple Inc."
    assert first_ent.label == "ORG"
    assert first_ent.start_char == 0
    assert first_ent.end_char == 10

    # Tickers and Sectors
    assert "AAPL" in result.tickers
    assert "Information Technology" in result.sectors


@pytest.mark.unit
@pytest.mark.issue_11
def test_ticker_normalization_and_gics_sectors() -> None:
    """Verify company names normalize to tickers and GICS sectors correctly."""
    text = "Microsoft Corp. and JPMorgan Chase announced a joint enterprise finance venture."

    def factory(t: str) -> MockDoc:
        return MockDoc(
            t,
            [
                MockSpan("Microsoft Corp.", "ORG", 0, 15),
                MockSpan("JPMorgan Chase", "ORG", 20, 34),
            ],
        )

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    result = extractor.extract_text(text)

    assert "MSFT" in result.tickers
    assert "JPM" in result.tickers
    assert "Information Technology" in result.sectors
    assert "Financials" in result.sectors


@pytest.mark.unit
@pytest.mark.issue_11
def test_cashtag_recognition() -> None:
    """Verify direct cashtags ($NVDA) in text are mapped to tickers and sectors."""
    text = "Traders are heavily accumulating $NVDA ahead of next week's GPU conference."

    def factory(t: str) -> MockDoc:
        return MockDoc(t, [])

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    result = extractor.extract_text(text)

    assert "NVDA" in result.tickers
    assert "Information Technology" in result.sectors


@pytest.mark.unit
@pytest.mark.issue_11
def test_batch_extraction() -> None:
    """Verify extract_batch processes texts in batch mode and maintains document order."""
    texts = [
        "Tesla delivered 500,000 electric vehicles.",
        "ExxonMobil expanded offshore drilling capacity.",
        "Pfizer received FDA approval for a new oncology therapy.",
    ]

    def factory(t: str) -> MockDoc:
        if "Tesla" in t:
            return MockDoc(t, [MockSpan("Tesla", "ORG", 0, 5)])
        if "ExxonMobil" in t:
            return MockDoc(t, [MockSpan("ExxonMobil", "ORG", 0, 10)])
        if "Pfizer" in t:
            return MockDoc(t, [MockSpan("Pfizer", "ORG", 0, 6)])
        return MockDoc(t, [])

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    results = extractor.extract_batch(texts, batch_size=2)

    assert len(results) == 3
    assert results[0].tickers == ["TSLA"]
    assert results[0].sectors == ["Consumer Discretionary"]
    assert results[1].tickers == ["XOM"]
    assert results[1].sectors == ["Energy"]
    assert results[2].tickers == ["PFE"]
    assert results[2].sectors == ["Health Care"]


@pytest.mark.unit
@pytest.mark.issue_11
def test_empty_and_whitespace_input() -> None:
    """Verify empty or whitespace strings return empty NERResult without error."""
    mock_nlp = MockSpaCyNLP()
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    res_empty = extractor.extract_text("")
    assert res_empty.tickers == []
    assert res_empty.sectors == []
    assert res_empty.entities == {}

    res_whitespace = extractor.extract_text("   \n\t  ")
    assert res_whitespace.tickers == []
    assert res_whitespace.sectors == []

    # Batch with empty strings
    batch_res = extractor.extract_batch(["", "  "])
    assert len(batch_res) == 2
    assert batch_res[0].tickers == []

    # Empty batch
    assert extractor.extract_batch([]) == []


@pytest.mark.unit
@pytest.mark.issue_11
def test_custom_lookup_injection() -> None:
    """Verify custom company-to-ticker and ticker-to-sector maps can be injected."""
    custom_company_map = {"acme rockets": "ACME"}
    custom_sector_map = {"ACME": "Aerospace & Defense"}

    def factory(t: str) -> MockDoc:
        return MockDoc(t, [MockSpan("Acme Rockets Inc.", "ORG", 0, 17)])

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(
        nlp=mock_nlp,
        company_to_ticker=custom_company_map,
        ticker_to_sector=custom_sector_map,
    )

    result = extractor.extract_text("Acme Rockets Inc. launches satellite.")

    assert result.tickers == ["ACME"]
    assert result.sectors == ["Aerospace & Defense"]


@pytest.mark.unit
@pytest.mark.issue_11
def test_org_without_ticker_no_hallucination() -> None:
    """Verify unknown private organizations do not produce false ticker mappings."""

    def factory(t: str) -> MockDoc:
        return MockDoc(t, [MockSpan("Joe's Corner Diner", "ORG", 0, 18)])

    mock_nlp = MockSpaCyNLP(doc_factory=factory)
    extractor = FinancialNERExtractor(nlp=mock_nlp)

    result = extractor.extract_text("Joe's Corner Diner opened a new location.")

    assert result.entities["ORG"] == ["Joe's Corner Diner"]
    assert result.tickers == []
    assert result.sectors == []


@pytest.mark.unit
@pytest.mark.issue_11
def test_lazy_loading_error_handling() -> None:
    """Verify RuntimeError is raised when SpaCy model is unavailable."""
    extractor = FinancialNERExtractor(model_name="non-existent-spacy-model")

    with pytest.raises(RuntimeError, match="SpaCy or model"):
        extractor._get_nlp()

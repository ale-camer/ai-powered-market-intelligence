"""Named Entity Recognition and financial sector tagging pipeline."""

import re
from collections.abc import Sequence
from typing import Any, cast

from market_intel.core.config import get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import EntityItem, NERResult

logger = get_logger(__name__)

TARGET_ENTITY_LABELS = frozenset({"ORG", "MONEY", "PERCENT", "DATE"})

# Suffixes to strip during company name normalization
CORPORATE_SUFFIXES_PATTERN = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|group|holdings|technologies|platforms)\b\.?",
    re.IGNORECASE,
)

# Canonical company name (normalized lowercase) -> Ticker Symbol
DEFAULT_COMPANY_TO_TICKER: dict[str, str] = {
    # Information Technology
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "broadcom": "AVGO",
    "oracle": "ORCL",
    "salesforce": "CRM",
    "adobe": "ADBE",
    "cisco": "CSCO",
    "intel": "INTC",
    "advanced micro devices": "AMD",
    "amd": "AMD",
    "qualcomm": "QCOM",
    "ibm": "IBM",
    "international business machines": "IBM",
    "servicenow": "NOW",
    "applied materials": "AMAT",
    # Communication Services
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "walt disney": "DIS",
    "disney": "DIS",
    "comcast": "CMCSA",
    "verizon": "VZ",
    "att": "T",
    "at&t": "T",
    # Consumer Discretionary
    "amazon": "AMZN",
    "tesla": "TSLA",
    "home depot": "HD",
    "mcdonalds": "MCD",
    "mcdonald's": "MCD",
    "nike": "NKE",
    "starbucks": "SBUX",
    "target": "TGT",
    "lowes": "LOW",
    "lowe's": "LOW",
    "booking": "BKNG",
    # Consumer Staples
    "procter gamble": "PG",
    "procter & gamble": "PG",
    "coca cola": "KO",
    "coca-cola": "KO",
    "pepsico": "PEP",
    "pepsi": "PEP",
    "walmart": "WMT",
    "costco": "COST",
    "philip morris": "PM",
    "mondelez": "MDLZ",
    # Energy
    "exxonmobil": "XOM",
    "exxon mobil": "XOM",
    "exxon": "XOM",
    "chevron": "CVX",
    "conocophillips": "COP",
    "schlumberger": "SLB",
    "eog resources": "EOG",
    "eog": "EOG",
    # Financials
    "jpmorgan chase": "JPM",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "j.p. morgan": "JPM",
    "bank of america": "BAC",
    "wells fargo": "WFC",
    "citigroup": "C",
    "citi": "C",
    "goldman sachs": "GS",
    "morgan stanley": "MS",
    "visa": "V",
    "mastercard": "MA",
    "berkshire hathaway": "BRK.B",
    "berkshire": "BRK.B",
    "blackrock": "BLK",
    # Health Care
    "unitedhealth": "UNH",
    "united health": "UNH",
    "johnson johnson": "JNJ",
    "johnson & johnson": "JNJ",
    "j&j": "JNJ",
    "eli lilly": "LLY",
    "pfizer": "PFE",
    "abbvie": "ABBV",
    "merck": "MRK",
    "thermo fisher": "TMO",
    "abbott": "ABT",
    # Industrials
    "boeing": "BA",
    "caterpillar": "CAT",
    "general electric": "GE",
    "ge": "GE",
    "honeywell": "HON",
    "union pacific": "UNP",
    "lockheed martin": "LMT",
    "rtx": "RTX",
    "raytheon": "RTX",
    "ups": "UPS",
    "united parcel service": "UPS",
    # Materials
    "linde": "LIN",
    "air products": "APD",
    "sherwin williams": "SHW",
    "sherwin-williams": "SHW",
    "freeport mcmoran": "FCX",
    "freeport-mcmoran": "FCX",
    "ecolab": "ECL",
    # Real Estate
    "prologis": "PLD",
    "american tower": "AMT",
    "equinix": "EQIX",
    "simon property": "SPG",
    "realty income": "O",
    # Utilities
    "nextera energy": "NEE",
    "nextera": "NEE",
    "southern company": "SO",
    "duke energy": "DUK",
    "constellation energy": "CEG",
}

# Ticker Symbol -> 11 Official GICS Sectors
TICKER_TO_GICS_SECTOR: dict[str, str] = {
    # Information Technology
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AVGO": "Information Technology",
    "ORCL": "Information Technology",
    "CRM": "Information Technology",
    "ADBE": "Information Technology",
    "CSCO": "Information Technology",
    "INTC": "Information Technology",
    "AMD": "Information Technology",
    "QCOM": "Information Technology",
    "IBM": "Information Technology",
    "NOW": "Information Technology",
    "AMAT": "Information Technology",
    # Communication Services
    "GOOGL": "Communication Services",
    "GOOG": "Communication Services",
    "META": "Communication Services",
    "NFLX": "Communication Services",
    "DIS": "Communication Services",
    "CMCSA": "Communication Services",
    "VZ": "Communication Services",
    "T": "Communication Services",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary",
    "TGT": "Consumer Discretionary",
    "LOW": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary",
    # Consumer Staples
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "PEP": "Consumer Staples",
    "WMT": "Consumer Staples",
    "COST": "Consumer Staples",
    "PM": "Consumer Staples",
    "MDLZ": "Consumer Staples",
    # Energy
    "XOM": "Energy",
    "CVX": "Energy",
    "COP": "Energy",
    "SLB": "Energy",
    "EOG": "Energy",
    # Financials
    "JPM": "Financials",
    "BAC": "Financials",
    "WFC": "Financials",
    "C": "Financials",
    "GS": "Financials",
    "MS": "Financials",
    "V": "Financials",
    "MA": "Financials",
    "BRK.A": "Financials",
    "BRK.B": "Financials",
    "BLK": "Financials",
    # Health Care
    "UNH": "Health Care",
    "JNJ": "Health Care",
    "LLY": "Health Care",
    "PFE": "Health Care",
    "ABBV": "Health Care",
    "MRK": "Health Care",
    "TMO": "Health Care",
    "ABT": "Health Care",
    # Industrials
    "BA": "Industrials",
    "CAT": "Industrials",
    "GE": "Industrials",
    "HON": "Industrials",
    "UNP": "Industrials",
    "LMT": "Industrials",
    "RTX": "Industrials",
    "UPS": "Industrials",
    # Materials
    "LIN": "Materials",
    "APD": "Materials",
    "SHW": "Materials",
    "FCX": "Materials",
    "ECL": "Materials",
    # Real Estate
    "PLD": "Real Estate",
    "AMT": "Real Estate",
    "EQIX": "Real Estate",
    "SPG": "Real Estate",
    "O": "Real Estate",
    # Utilities
    "NEE": "Utilities",
    "SO": "Utilities",
    "DUK": "Utilities",
    "CEG": "Utilities",
}

CASHTAG_PATTERN = re.compile(r"\$([A-Z]{1,5})\b")


def normalize_company_name(name: str) -> str:
    """Normalize company name by stripping legal suffixes and punctuation."""
    cleaned = name.strip().lower()
    cleaned = CORPORATE_SUFFIXES_PATTERN.sub("", cleaned)
    # Remove extra whitespace and special characters
    cleaned = re.sub(r"[^\w\s&]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class FinancialNERExtractor:
    """Financial Named Entity Recognition and Sector Tagging pipeline.

    Extracts ORG, MONEY, PERCENT, and DATE entities via SpaCy transformer
    models, normalizes organizations to ticker symbols, and assigns GICS
    sector classifications.
    """

    def __init__(
        self,
        model_name: str | None = None,
        nlp: object | None = None,
        company_to_ticker: dict[str, str] | None = None,
        ticker_to_sector: dict[str, str] | None = None,
    ) -> None:
        """Initialize the Financial NER extractor.

        Args:
            model_name: SpaCy model identifier (default: en_core_web_trf).
            nlp: Optional pre-loaded SpaCy Language instance (for testing).
            company_to_ticker: Optional custom company-to-ticker mapping.
            ticker_to_sector: Optional custom ticker-to-GICS sector mapping.
        """
        settings = get_settings()
        self.model_name = model_name or settings.spacy_ner_model
        self._nlp = nlp
        self.company_to_ticker = (
            company_to_ticker if company_to_ticker is not None else dict(DEFAULT_COMPANY_TO_TICKER)
        )
        self.ticker_to_sector = (
            ticker_to_sector if ticker_to_sector is not None else dict(TICKER_TO_GICS_SECTOR)
        )

    def _get_nlp(self) -> object:
        """Lazy-load SpaCy model."""
        if self._nlp is None:
            try:
                import spacy

                logger.info("Loading SpaCy NER model: %s", self.model_name)
                self._nlp = spacy.load(self.model_name)
            except Exception as exc:
                logger.error("Failed to load SpaCy model %s: %s", self.model_name, exc)
                raise RuntimeError(f"SpaCy or model {self.model_name} unavailable: {exc}") from exc
        return self._nlp

    def _process_doc(self, text: str, doc: object) -> NERResult:
        """Transform a SpaCy Doc object into a standardized NERResult."""
        entities_by_label: dict[str, list[str]] = {
            "ORG": [],
            "MONEY": [],
            "PERCENT": [],
            "DATE": [],
        }
        detailed_entities: list[EntityItem] = []
        identified_tickers: list[str] = []

        ents = getattr(doc, "ents", [])
        for ent in ents:
            label = str(getattr(ent, "label_", "")).upper()
            if label not in TARGET_ENTITY_LABELS:
                continue

            ent_text = str(getattr(ent, "text", "")).strip()
            if not ent_text:
                continue

            if ent_text not in entities_by_label[label]:
                entities_by_label[label].append(ent_text)

            start_char = getattr(ent, "start_char", None)
            end_char = getattr(ent, "end_char", None)
            detailed_entities.append(
                EntityItem(
                    text=ent_text,
                    label=label,
                    start_char=start_char,
                    end_char=end_char,
                )
            )

            # Check ORG for company -> ticker mapping
            if label == "ORG":
                norm_name = normalize_company_name(ent_text)
                ticker = self.company_to_ticker.get(norm_name)
                if ticker and ticker not in identified_tickers:
                    identified_tickers.append(ticker)

        # Detect direct cashtags in text ($AAPL, $MSFT)
        for match in CASHTAG_PATTERN.finditer(text):
            cashtag = match.group(1).upper()
            if cashtag in self.ticker_to_sector and cashtag not in identified_tickers:
                identified_tickers.append(cashtag)

        # Map tickers to GICS sectors
        identified_sectors: list[str] = []
        for ticker in identified_tickers:
            sector = self.ticker_to_sector.get(ticker)
            if sector and sector not in identified_sectors:
                identified_sectors.append(sector)

        # Filter out empty entity categories
        clean_entities = {k: v for k, v in entities_by_label.items() if v}

        return NERResult(
            entities=clean_entities,
            tickers=identified_tickers,
            sectors=identified_sectors,
            detailed_entities=detailed_entities,
            model_used=self.model_name,
        )

    def extract_text(self, text: str) -> NERResult:
        """Extract financial named entities and sector tags from a single text."""
        if not text or not text.strip():
            return NERResult(model_used=self.model_name)

        nlp = self._get_nlp()
        doc = cast(Any, nlp)(text)
        return self._process_doc(text, doc)

    def extract_batch(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
    ) -> list[NERResult]:
        """Extract financial entities from a batch of texts using nlp.pipe when available.

        Args:
            texts: Sequence of strings to process.
            batch_size: Batch size for pipeline processing.

        Returns:
            List of NERResult models corresponding to inputs.
        """
        if not texts:
            return []

        nlp = self._get_nlp()
        results: list[NERResult] = []

        if hasattr(nlp, "pipe"):
            docs = cast(Any, nlp).pipe(texts, batch_size=batch_size)
            for text, doc in zip(texts, docs, strict=True):
                if not text or not text.strip():
                    results.append(NERResult(model_used=self.model_name))
                else:
                    results.append(self._process_doc(text, doc))
        else:
            for text in texts:
                results.append(self.extract_text(text))

        return results

"""Financial sentiment analysis pipeline using FinBERT and GPT-4o fallback."""

import json
from collections.abc import Sequence
from typing import Any, cast

from market_intel.core.config import get_settings
from market_intel.core.logger import get_logger
from market_intel.core.schemas import SentimentResult

logger = get_logger(__name__)

FINBERT_DEFAULT_MODEL = "ProsusAI/finbert"
GPT4O_DEFAULT_MODEL = "gpt-4o"
DEFAULT_CONFIDENCE_THRESHOLD = 0.65
DEFAULT_MIN_TEXT_LENGTH = 30
DEFAULT_BATCH_SIZE = 32

OPENAI_SENTIMENT_SYSTEM_PROMPT = (
    "You are an expert financial market analyst. Analyze the financial sentiment "
    "of the provided text. Respond strictly with a JSON object containing:\n"
    '- "label": one of "positive", "negative", or "neutral"\n'
    '- "score": float from -1.0 (extremely bearish/negative) to 1.0 (extremely bullish/positive)\n'
    '- "confidence": float from 0.0 to 1.0\n'
    '- "explanation": concise 1-2 sentence explanation of your classification'
)


class SentimentAnalyzer:
    """Production financial sentiment analysis pipeline.

    Combines HuggingFace FinBERT for high-throughput batch scoring with
    automatic GPT-4o fallback for ambiguous, low-confidence, or short texts.
    """

    def __init__(
        self,
        finbert_model_name: str | None = None,
        openai_model: str | None = None,
        confidence_threshold: float | None = None,
        min_text_length: int | None = None,
        batch_size: int | None = None,
        model: object | None = None,
        tokenizer: object | None = None,
        openai_client: object | None = None,
    ) -> None:
        """Initialize the SentimentAnalyzer pipeline.

        Args:
            finbert_model_name: HuggingFace model repo ID (default: ProsusAI/finbert).
            openai_model: OpenAI model name for fallback (default: gpt-4o or from settings).
            confidence_threshold: Minimum confidence score to accept FinBERT output.
            min_text_length: Minimum text character length before triggering fallback.
            batch_size: Default batch size for batch inference.
            model: Optional pre-loaded PyTorch model (for testing or custom inference).
            tokenizer: Optional pre-loaded HuggingFace tokenizer.
            openai_client: Optional pre-configured OpenAI client (for testing).
        """
        settings = get_settings()

        self.finbert_model_name = finbert_model_name or settings.finbert_model_name
        self.openai_model = openai_model or settings.openai_model or GPT4O_DEFAULT_MODEL
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.sentiment_confidence_threshold
        )
        self.min_text_length = (
            min_text_length if min_text_length is not None else settings.sentiment_min_text_length
        )
        self.batch_size = batch_size if batch_size is not None else settings.sentiment_batch_size

        self._model = model
        self._tokenizer = tokenizer
        self._openai_client = openai_client

    def _get_model_and_tokenizer(self) -> tuple[Any, Any]:
        """Lazy-load HuggingFace FinBERT model and tokenizer."""
        if self._model is None or self._tokenizer is None:
            try:
                import torch
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                )

                logger.info("Loading FinBERT model: %s", self.finbert_model_name)
                self._tokenizer = AutoTokenizer.from_pretrained(self.finbert_model_name)
                loaded_model = AutoModelForSequenceClassification.from_pretrained(
                    self.finbert_model_name
                )
                loaded_model.eval()
                if torch.cuda.is_available():
                    loaded_model.to("cuda")
                self._model = loaded_model
            except Exception as exc:
                logger.error("Failed to load FinBERT model %s: %s", self.finbert_model_name, exc)
                raise RuntimeError(
                    f"FinBERT dependencies unavailable or model loading failed: {exc}"
                ) from exc

        return self._model, self._tokenizer

    def _get_openai_client(self) -> object | None:
        """Return configured OpenAI client instance."""
        if self._openai_client is None:
            try:
                from openai import OpenAI

                api_key = get_settings().openai_api_key
                if not api_key:
                    logger.warning("OPENAI_API_KEY is not configured; fallback disabled.")
                    return None
                self._openai_client = OpenAI(api_key=api_key)
            except Exception as exc:
                logger.warning("Failed to initialize OpenAI client: %s", exc)
                return None
        return self._openai_client

    def is_short_text(self, text: str) -> bool:
        """Determine if text has insufficient context for FinBERT."""
        cleaned = text.strip()
        if len(cleaned) < self.min_text_length:
            return True
        words = cleaned.split()
        return len(words) < 5

    def is_ambiguous(self, confidence: float, probs: dict[str, float]) -> bool:
        """Determine if FinBERT probability distribution is ambiguous."""
        if confidence < self.confidence_threshold:
            return True

        # Check if positive and negative probabilities are too close without dominant neutral
        p_pos = probs.get("positive", 0.0)
        p_neg = probs.get("negative", 0.0)
        p_neu = probs.get("neutral", 0.0)
        return bool(abs(p_pos - p_neg) < 0.15 and p_neu < 0.50)

    def _infer_finbert_batch(self, texts: Sequence[str]) -> list[dict[str, Any]]:
        """Run batch inference on FinBERT model."""
        model, tokenizer = self._get_model_and_tokenizer()

        # Handle mock model in tests
        if hasattr(model, "predict_batch"):
            return model.predict_batch(texts)  # type: ignore[no-any-return]

        import torch

        model_any = cast(Any, model)
        tokenizer_any = cast(Any, tokenizer)

        inputs = tokenizer_any(
            list(texts),
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        device = next(model_any.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model_any(**inputs)
            logits = outputs.logits
            probabilities = torch.softmax(logits, dim=-1).cpu().numpy()

        id2label = getattr(
            model_any.config,
            "id2label",
            {0: "positive", 1: "negative", 2: "neutral"},
        )
        # Normalize label keys to lowercase
        label_map = {int(k): str(v).lower() for k, v in id2label.items()}

        results: list[dict[str, Any]] = []
        for prob_vec in probabilities:
            prob_dict: dict[str, float] = {}
            for idx, prob in enumerate(prob_vec):
                label_name = label_map.get(idx, f"label_{idx}")
                prob_dict[label_name] = float(prob)

            best_label = max(prob_dict, key=prob_dict.get)  # type: ignore[arg-type]
            confidence = prob_dict[best_label]

            # Compound financial score: positive prob - negative prob
            score = prob_dict.get("positive", 0.0) - prob_dict.get("negative", 0.0)
            score = max(-1.0, min(1.0, score))

            results.append(
                {
                    "label": best_label,
                    "score": round(score, 4),
                    "confidence": round(confidence, 4),
                    "probs": prob_dict,
                }
            )

        return results

    def _fallback_gpt4o(self, text: str) -> SentimentResult | None:
        """Call GPT-4o for nuanced financial sentiment analysis."""
        client = self._get_openai_client()
        if client is None:
            return None

        try:
            logger.info("Executing GPT-4o sentiment fallback for text: %s...", text[:50])
            client_any = cast(Any, client)
            response = client_any.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": OPENAI_SENTIMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Financial Text:\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if not content:
                return None

            data = json.loads(content)
            label = str(data.get("label", "neutral")).lower()
            if label not in {"positive", "negative", "neutral"}:
                label = "neutral"

            raw_score = float(data.get("score", 0.0))
            score = max(-1.0, min(1.0, raw_score))
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.85))))
            explanation = data.get("explanation")

            return SentimentResult(
                label=label,
                score=round(score, 4),
                model_used=self.openai_model,
                confidence=round(confidence, 4),
                explanation=explanation,
            )
        except Exception as exc:
            logger.warning("GPT-4o fallback failed: %s", exc)
            return None

    def analyze_text(self, text: str) -> SentimentResult:
        """Analyze sentiment of a single financial text document."""
        return self.analyze_batch([text])[0]

    def analyze_batch(
        self,
        texts: Sequence[str],
        batch_size: int | None = None,
    ) -> list[SentimentResult]:
        """Analyze sentiment for a collection of financial texts in batches.

        Processes items with FinBERT in chunks of `batch_size`. For items that are
        ambiguous or too short, triggers the GPT-4o fallback mechanism.

        Args:
            texts: List or sequence of texts to classify.
            batch_size: Override batch size for inference.

        Returns:
            List of SentimentResult objects corresponding to input texts.
        """
        if not texts:
            return []

        effective_batch_size = max(1, batch_size or self.batch_size)
        results: list[SentimentResult] = []

        for i in range(0, len(texts), effective_batch_size):
            batch_texts = list(texts[i : i + effective_batch_size])

            # Pre-filter empty/whitespace texts
            processed_indices: list[int] = []
            non_empty_texts: list[str] = []

            for idx, text in enumerate(batch_texts):
                if not text or not text.strip():
                    continue
                processed_indices.append(idx)
                non_empty_texts.append(text)

            # Initialize batch results placeholder with neutral defaults
            batch_results: list[SentimentResult | None] = [
                SentimentResult(
                    label="neutral",
                    score=0.0,
                    model_used=self.finbert_model_name,
                    confidence=1.0,
                    explanation="Empty or whitespace text",
                )
                if not text or not text.strip()
                else None
                for text in batch_texts
            ]

            if non_empty_texts:
                finbert_outputs = self._infer_finbert_batch(non_empty_texts)

                for orig_idx, text, output in zip(
                    processed_indices,
                    non_empty_texts,
                    finbert_outputs,
                    strict=True,
                ):
                    label = output["label"]
                    score = output["score"]
                    confidence = output["confidence"]
                    probs = output.get("probs", {})

                    needs_fallback = self.is_short_text(text) or self.is_ambiguous(
                        confidence, probs
                    )

                    if needs_fallback:
                        fallback_res = self._fallback_gpt4o(text)
                        if fallback_res is not None:
                            batch_results[orig_idx] = fallback_res
                            continue

                    # Fallback not needed or failed, use FinBERT result
                    batch_results[orig_idx] = SentimentResult(
                        label=label,
                        score=score,
                        model_used=self.finbert_model_name,
                        confidence=confidence,
                        explanation=None,
                    )

            for item in batch_results:
                if item is not None:
                    results.append(item)

        return results

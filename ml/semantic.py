"""Match a student's own words ("I love cooking and travelling") to careers by meaning.

Two methods, the best one available is used and its name is always reported:
  * "sbert"  Sentence-BERT (sentence-transformers, model all-MiniLM-L6-v2): turns each text into a
             384-number vector so that texts with similar MEANING are close, even with different
             words ("doctor" ~ "physician"). Needs `pip install sentence-transformers` and downloads
             the model (~90 MB) the first time.
  * "tfidf"  TF-IDF + cosine similarity (scikit-learn): matches shared WORDS, weighted by how rare
             they are. Always available, no download. Used when sentence-transformers is missing.

Each career is described by its short title, official title, other job titles and O*NET
description. Career vectors are computed once and cached in data/processed/ (re-built when the
careers or the model change). Similarity is cosine similarity (0 = unrelated, 1 = same direction).

This is a separate "matches for what you wrote" list. It is NOT mixed into the profile match score:
choosing weights for a hybrid needs real survey data (see CLAUDE.md, roadmap item 5).
"""
import hashlib
import logging
import os
import threading
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "processed"
SBERT_MODEL = os.getenv("SEMANTIC_MODEL", "all-MiniLM-L6-v2")
MAX_ALT_TITLES = 10

log = logging.getLogger("pathfinder.semantic")


def career_text(data, code):
    """The text that represents one career."""
    occ = data["occupations"].loc[code]
    short = data.get("short_title")
    parts = [str(short[code]) if short is not None and code in short.index else "", str(occ["Title"])]
    alt = data.get("alt_titles", {})
    parts += [str(t) for t in list(alt.get(code, []))[:MAX_ALT_TITLES]]
    parts.append(str(occ.get("Description") or ""))
    return ". ".join(p for p in parts if p and p != "nan")


def sbert_available():
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


class _TfidfEncoder:
    name = "tfidf"

    def fit(self, texts):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, ngram_range=(1, 2), min_df=1)
        self.vectorizer.fit(texts)
        return self

    def encode(self, texts):
        m = self.vectorizer.transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        return m / np.where(norms == 0, 1, norms)


class _SbertEncoder:
    def __init__(self, model_name=SBERT_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.name = f"sbert:{model_name}"

    def fit(self, texts):
        return self

    def encode(self, texts):
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True, batch_size=64,
                                            show_progress_bar=False), dtype=np.float32)


class SemanticMatcher:
    """matcher = SemanticMatcher(data); matcher.match("I like cooking", top_n=10) -> [(code, similarity)]"""

    def __init__(self, data, encoder=None, cache_dir=CACHE_DIR, prefer_sbert=True):
        self.data = data
        self.codes = list(data["codes"])                     # ranked careers, India exclusions already removed
        self.texts = [career_text(data, c) for c in self.codes]
        if encoder is None:
            if prefer_sbert and sbert_available():
                try:
                    encoder = _SbertEncoder()
                except Exception as err:                   # model download blocked, no internet ...
                    log.warning("Sentence-BERT could not load (%s); using TF-IDF instead", err)
            encoder = encoder or _TfidfEncoder()
        self.encoder = encoder.fit(self.texts)
        self.method = getattr(self.encoder, "name", "custom")
        self.vectors = self._career_vectors(Path(cache_dir) if cache_dir else None)

    def _career_vectors(self, cache_dir):
        if not self.method.startswith("sbert") or cache_dir is None:
            return self.encoder.encode(self.texts)         # TF-IDF is fast; no cache needed
        key = hashlib.sha1(("\n".join(self.codes) + "\n".join(self.texts) + self.method).encode()).hexdigest()[:16]
        path = cache_dir / f"career_embeddings_{key}.npy"
        if path.exists():
            return np.load(path)
        vectors = self.encoder.encode(self.texts)
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(path, vectors)
        return vectors

    def match(self, text, top_n=10, codes=None):
        """Careers most similar to the text, best first: [(code, cosine similarity rounded to 3)]."""
        text = (text or "").strip()
        if not text:
            return []
        q = self.encoder.encode([text])[0]
        sims = self.vectors @ q
        allowed = None if codes is None else set(codes)
        order = np.argsort(-sims, kind="stable")
        out = []
        for i in order:
            if allowed is not None and self.codes[i] not in allowed:
                continue
            if sims[i] <= 0:
                break
            out.append((self.codes[i], round(float(sims[i]), 3)))
            if len(out) == top_n:
                break
        return out


class LazyMatcher:
    """Builds the matcher in a background thread at startup, so the server starts at once."""

    def __init__(self, data, **kwargs):
        self._matcher, self._error = None, None
        self._ready = threading.Event()
        threading.Thread(target=self._build, args=(data,), kwargs=kwargs, daemon=True).start()

    def _build(self, data, **kwargs):
        try:
            self._matcher = SemanticMatcher(data, **kwargs)
            log.info("Semantic matcher ready (%s, %d careers)", self._matcher.method, len(self._matcher.codes))
        except Exception as err:
            self._error = err
            log.exception("Semantic matcher failed")
        finally:
            self._ready.set()

    def get(self, timeout=60):
        """The matcher, waiting up to `timeout` seconds for it to finish building. None if not ready."""
        self._ready.wait(timeout)
        return self._matcher

    @property
    def error(self):
        return self._error

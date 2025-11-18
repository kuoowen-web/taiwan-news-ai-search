"""
BM25 (Best Match 25) ranking algorithm for hybrid search.

This module implements the BM25 probabilistic ranking function for calculating
keyword relevance scores between queries and documents.

References:
- Robertson, S. E., & Zaragoza, H. (2009). "The Probabilistic Relevance Framework: BM25 and Beyond"
- https://en.wikipedia.org/wiki/Okapi_BM25
"""

import re
import math
from typing import List, Dict, Tuple
from collections import Counter


class BM25Scorer:
    """
    BM25 ranking algorithm scorer.

    BM25 calculates relevance scores based on term frequency (TF), inverse document
    frequency (IDF), and document length normalization.

    Formula:
        BM25(D, Q) = Σ IDF(qᵢ) × (f(qᵢ, D) × (k₁ + 1)) / (f(qᵢ, D) + k₁ × (1 - b + b × (|D| / avgdl)))

    Where:
        - f(qᵢ, D) = term frequency of qᵢ in document D
        - |D| = length of document D (in tokens)
        - avgdl = average document length in the corpus
        - k₁ = term saturation parameter (default: 1.5)
        - b = length normalization parameter (default: 0.75)
        - IDF(qᵢ) = log((N - n(qᵢ) + 0.5) / (n(qᵢ) + 0.5) + 1)
            - N = total number of documents
            - n(qᵢ) = number of documents containing qᵢ
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 scorer with parameters.

        Args:
            k1: Term saturation parameter (typical range: 1.2-2.0)
                Higher values give more weight to term frequency
            b: Length normalization parameter (typical range: 0.5-0.9)
                Higher values penalize longer documents more
        """
        self.k1 = k1
        self.b = b

    def tokenize(self, text: str) -> List[str]:
        """
        Extract tokens from Chinese and English text.

        Uses the same tokenization strategy as Qdrant hybrid search:
        - Chinese: Extract 2, 3, and 4 character sequences
        - English: Extract words with 2+ characters, lowercased

        Args:
            text: Input text to tokenize

        Returns:
            List of tokens (Chinese character sequences and English words)
        """
        if not text:
            return []

        tokens = []

        # Extract Chinese text
        chinese_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', text))
        if chinese_text:
            # Extract 2-character sequences
            for i in range(len(chinese_text) - 1):
                word = chinese_text[i:i+2]
                tokens.append(word)
            # Extract 3-character sequences
            for i in range(len(chinese_text) - 2):
                word = chinese_text[i:i+3]
                tokens.append(word)
            # Extract 4-character sequences
            for i in range(len(chinese_text) - 3):
                word = chinese_text[i:i+4]
                tokens.append(word)

        # Extract English words (2+ characters, lowercased)
        english_words = [w.lower() for w in re.findall(r'[a-zA-Z]{2,}', text)]
        tokens.extend(english_words)

        return tokens

    def calculate_idf(self, term: str, doc_count: int, term_doc_count: int) -> float:
        """
        Calculate inverse document frequency (IDF) for a term.

        Formula:
            IDF(term) = log((N - n(term) + 0.5) / (n(term) + 0.5) + 1)

        Args:
            term: The term to calculate IDF for
            doc_count: Total number of documents (N)
            term_doc_count: Number of documents containing the term (n)

        Returns:
            IDF score (higher = more rare/discriminative term)
        """
        # Avoid division by zero
        if term_doc_count == 0:
            return 0.0

        # BM25 IDF formula
        numerator = doc_count - term_doc_count + 0.5
        denominator = term_doc_count + 0.5
        idf = math.log((numerator / denominator) + 1)

        return idf

    def calculate_score(
        self,
        query_tokens: List[str],
        document_text: str,
        avg_doc_length: float,
        corpus_size: int,
        term_doc_counts: Dict[str, int]
    ) -> float:
        """
        Calculate BM25 score for a query-document pair.

        Args:
            query_tokens: List of tokens from the query
            document_text: The document text to score
            avg_doc_length: Average document length in the corpus (in tokens)
            corpus_size: Total number of documents in the corpus
            term_doc_counts: Dictionary mapping terms to document frequency counts

        Returns:
            BM25 relevance score (higher = more relevant)
        """
        if not query_tokens or not document_text:
            return 0.0

        # Tokenize the document
        doc_tokens = self.tokenize(document_text)
        doc_length = len(doc_tokens)

        # Avoid division by zero
        if doc_length == 0 or avg_doc_length == 0:
            return 0.0

        # Count term frequencies in document
        doc_term_freqs = Counter(doc_tokens)

        # Calculate BM25 score
        score = 0.0
        for term in set(query_tokens):  # Use set to avoid counting same term multiple times
            # Term frequency in document
            tf = doc_term_freqs.get(term, 0)

            if tf == 0:
                continue  # Term not in document

            # Document frequency (how many docs contain this term)
            df = term_doc_counts.get(term, 0)

            # Calculate IDF
            idf = self.calculate_idf(term, corpus_size, df)

            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / avg_doc_length))

            term_score = idf * (numerator / denominator)
            score += term_score

        return score

    def calculate_corpus_stats(
        self,
        documents: List[Dict],
        title_field: str = 'name',
        description_field: str = 'description'
    ) -> Tuple[float, Dict[str, int]]:
        """
        Calculate corpus statistics needed for BM25 scoring.

        Args:
            documents: List of document dictionaries
            title_field: Field name for document title
            description_field: Field name for document description

        Returns:
            Tuple of (average_doc_length, term_doc_counts)
            - average_doc_length: Average number of tokens per document
            - term_doc_counts: Dictionary mapping each term to number of docs containing it
        """
        total_tokens = 0
        term_doc_presence = {}  # Set of doc indices containing each term

        for doc_idx, doc in enumerate(documents):
            # Combine title and description for full document text
            title = doc.get(title_field, '')
            description = doc.get(description_field, '')

            # Weight title tokens more heavily by including them 3 times
            doc_text = f"{title} {title} {title} {description}"

            # Tokenize
            tokens = self.tokenize(doc_text)
            total_tokens += len(tokens)

            # Track which documents contain which terms
            unique_tokens = set(tokens)
            for term in unique_tokens:
                if term not in term_doc_presence:
                    term_doc_presence[term] = set()
                term_doc_presence[term].add(doc_idx)

        # Calculate average document length
        avg_doc_length = total_tokens / len(documents) if documents else 0.0

        # Convert sets to counts
        term_doc_counts = {term: len(doc_set) for term, doc_set in term_doc_presence.items()}

        return avg_doc_length, term_doc_counts

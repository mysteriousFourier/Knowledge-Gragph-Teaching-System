"""Canonical outline for the structured ESQT graph."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


BOOK_TITLE = "Evolution and Selection of Quantitative Traits"


@dataclass(frozen=True)
class OutlinePart:
    id: str
    label: str
    chapter_start: int
    chapter_end: int


BOOK_PARTS: tuple[OutlinePart, ...] = (
    OutlinePart("part::1", "I. INTRODUCTION", 1, 1),
    OutlinePart("part::2", "II. EVOLUTION AT ONE AND TWO LOCI", 2, 10),
    OutlinePart("part::3", "III. DRIFT AND QUANTITATIVE TRAITS", 11, 12),
    OutlinePart("part::4", "IV. SHORT-TERM RESPONSE ON A SINGLE CHARACTER", 13, 20),
    OutlinePart("part::5", "V. SELECTION IN STRUCTURED POPULATIONS", 21, 23),
    OutlinePart("part::6", "VI. POPULATION-GENETIC MODELS OF TRAIT RESPONSE", 24, 28),
    OutlinePart("part::7", "VII. MEASURING SELECTION ON TRAITS", 29, 30),
)

APPENDICES_PART_ID = "part::appendices"
APPENDICES_PART_LABEL = "VIII. APPENDICES"


CANONICAL_CHAPTER_TITLES: dict[str, str] = {
    "chapter1": "Changes in Quantitative Traits Over Time",
    "chapter2": "Neutral Evolution in One- and Two-Locus Systems",
    "chapter3": "The Genetic Effective Size of a Population",
    "chapter4": "The Nonadaptive Forces of Evolution",
    "chapter5": "The Population Genetics of Selection",
    "chapter6": "Theorems of Natural Selection: Results of Price, Fisher, and Robertson",
    "chapter7": "Interaction of Selection, Mutation, and Drift",
    "chapter8": "Hitchhiking and Selective Sweeps",
    "chapter9": "Using Molecular Data to Detect Selection: Signatures from Recent Single Events",
    "chapter10": "Using Molecular Data to Detect Selection: Signatures from Multiple Historical Events",
    "chapter11": "Changes in Genetic Variance Induced by Drift",
    "chapter12": "The Neutral Divergence of Quantitative Traits",
    "chapter13": "Short-term Changes in the Mean: 1. The Breeder's Equation",
    "chapter14": "Short-term Changes in the Mean: 2. Truncation and Threshold Selection",
    "chapter15": "Short-term Changes in the Mean: 3. Permanent Versus Transient Response",
    "chapter16": "Short-term Changes in the Variance: 1. Changes in the Additive Variance",
    "chapter17": "Short-term Changes in the Variance: 2. Changes in the Environmental Variance",
    "chapter18": "Analysis of Short-term Selection Experiments: 1. Least-squares Approaches",
    "chapter19": "Analysis of Short-term Selection Experiments: 2. Mixed-model and Bayesian Approaches",
    "chapter20": "Selection Response in Natural Populations",
    "chapter21": "Family-Based Selection",
    "chapter22": "Associative Effects: Competition, Social Interactions, Group and Kin Selection",
    "chapter23": "Selection Under Inbreeding",
    "chapter24": "The Infinitesimal Model and Its Extensions",
    "chapter25": "Long-term Response: 1. Deterministic Aspects",
    "chapter26": "Long-term Response: 2. Finite Population Size and Mutation",
    "chapter27": "Long-term Response: 3. Adaptive Walks",
    "chapter28": "Maintenance of Quantitative Genetic Variation",
    "chapter29": "Individual Fitness and the Measurement of Univariate Selection",
    "chapter30": "Measuring Multivariate Selection",
    "appendix1": "Diffusion Theory",
    "appendix2": "Introduction to Bayesian Analysis",
    "appendix3": "Markov Chain Monte Carlo and Gibbs Sampling",
    "appendix4": "Multiple Comparisons: Bonferroni Corrections, False-Discovery Rates, and Meta-Analysis",
    "appendix5": "The Geometry of Vectors and Matrices: Eigenvalues and Eigenvectors",
    "appendix6": "Derivatives of Vectors and Vector-valued Functions",
}


def part_for_chapter(chapter: str) -> Optional[OutlinePart]:
    number = chapter_number(chapter)
    if number is None:
        return None
    for part in BOOK_PARTS:
        if part.chapter_start <= number <= part.chapter_end:
            return part
    return None


def chapter_number(chapter: str) -> Optional[int]:
    value = str(chapter or "").strip().lower()
    if not value.startswith("chapter"):
        return None
    try:
        return int(value.removeprefix("chapter"))
    except ValueError:
        return None


def appendix_number(chapter: str) -> Optional[int]:
    value = str(chapter or "").strip().lower()
    if not value.startswith("appendix"):
        return None
    try:
        return int(value.removeprefix("appendix"))
    except ValueError:
        return None

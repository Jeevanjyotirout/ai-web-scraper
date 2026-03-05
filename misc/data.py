"""
data.py
-------
Article data models and sample dataset used by both exporters.
"""

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Article:
    id: int
    title: str
    author: str
    category: str
    date: str
    word_count: int
    reads: int
    likes: int
    status: str          # Published / Draft / Review
    summary: str
    tags: list[str] = field(default_factory=list)

    @property
    def engagement_rate(self) -> float:
        return round((self.likes / self.reads * 100), 2) if self.reads else 0.0


# ── Sample Dataset ────────────────────────────────────────────────────────────
ARTICLES: list[Article] = [
    Article(
        id=1,
        title="The Future of Artificial Intelligence in Healthcare",
        author="Dr. Emily Carter",
        category="Technology",
        date="2024-03-15",
        word_count=2850,
        reads=14_320,
        likes=1_102,
        status="Published",
        summary=(
            "An in-depth exploration of how AI-powered diagnostics, predictive analytics, "
            "and robotic surgery are transforming patient outcomes and hospital efficiency. "
            "The article examines real-world deployments across leading medical institutions "
            "and highlights ethical considerations surrounding algorithmic bias."
        ),
        tags=["AI", "Healthcare", "Machine Learning", "Ethics"],
    ),
    Article(
        id=2,
        title="Sustainable Architecture: Building for the Next Century",
        author="Prof. James Alderton",
        category="Environment",
        date="2024-04-02",
        word_count=3_120,
        reads=9_870,
        likes=870,
        status="Published",
        summary=(
            "A comprehensive review of net-zero building techniques, biophilic design principles, "
            "and circular material economies. Case studies from Copenhagen, Singapore, and "
            "Masdar City illustrate how cities are redefining the relationship between the "
            "built environment and ecological systems."
        ),
        tags=["Architecture", "Sustainability", "Green Design", "Urban Planning"],
    ),
    Article(
        id=3,
        title="Quantum Computing: Breaking Through the Noise Barrier",
        author="Dr. Sarah Lin",
        category="Technology",
        date="2024-04-18",
        word_count=4_200,
        reads=21_050,
        likes=2_310,
        status="Published",
        summary=(
            "This article demystifies qubit decoherence and error-correction strategies "
            "that are bringing fault-tolerant quantum computers within reach. It covers "
            "recent milestones from IBM, Google, and IonQ, and forecasts commercial "
            "applications in cryptography, drug discovery, and logistics optimisation."
        ),
        tags=["Quantum", "Computing", "Physics", "Cryptography"],
    ),
    Article(
        id=4,
        title="The Psychology of Remote Work: Productivity, Isolation, and Balance",
        author="Dr. Marcus Webb",
        category="Business",
        date="2024-05-05",
        word_count=2_650,
        reads=18_400,
        likes=1_780,
        status="Published",
        summary=(
            "Drawing on longitudinal survey data from 4,000 remote workers across 12 countries, "
            "this piece analyses the cognitive and emotional dimensions of distributed work. "
            "It presents evidence-based frameworks for managers and individuals seeking to "
            "sustain high performance while protecting mental health."
        ),
        tags=["Remote Work", "Psychology", "Productivity", "Wellbeing"],
    ),
    Article(
        id=5,
        title="Ocean Carbon Capture: Science, Scale, and Controversy",
        author="Dr. Priya Nair",
        category="Environment",
        date="2024-05-22",
        word_count=3_480,
        reads=7_630,
        likes=640,
        status="Published",
        summary=(
            "Explores emerging ocean-based carbon removal strategies—from iron fertilisation "
            "to alkalinity enhancement—and weighs their gigaton-scale potential against "
            "ecological risks. The article calls for international governance frameworks "
            "before large-scale commercial deployment begins."
        ),
        tags=["Climate", "Ocean", "Carbon Capture", "Policy"],
    ),
    Article(
        id=6,
        title="Decentralised Finance: Promise, Peril, and Regulation",
        author="Nina Okafor",
        category="Finance",
        date="2024-06-10",
        word_count=3_900,
        reads=25_100,
        likes=3_050,
        status="Published",
        summary=(
            "A rigorous examination of DeFi protocols—DEXs, lending platforms, and yield "
            "aggregators—contrasting their democratising potential with systemic risks "
            "exposed by high-profile exploits. Reviews the evolving regulatory landscape "
            "in the EU, US, and Asia-Pacific."
        ),
        tags=["DeFi", "Blockchain", "Finance", "Regulation"],
    ),
    Article(
        id=7,
        title="Neuroplasticity and Lifelong Learning: Rewiring the Adult Brain",
        author="Prof. Daniel Rossi",
        category="Science",
        date="2024-06-28",
        word_count=2_970,
        reads=12_800,
        likes=1_430,
        status="Review",
        summary=(
            "Synthesises decades of neuroscience research to challenge the myth that "
            "adult brains are fixed. Practical implications for education, rehabilitation, "
            "and cognitive longevity are illustrated through clinical trials and "
            "first-person case narratives."
        ),
        tags=["Neuroscience", "Learning", "Brain", "Education"],
    ),
    Article(
        id=8,
        title="Supply Chain Resilience in a Multipolar World",
        author="Dr. Anna Kovacs",
        category="Business",
        date="2024-07-14",
        word_count=3_340,
        reads=6_950,
        likes=490,
        status="Draft",
        summary=(
            "Analyses how geopolitical fragmentation, climate disruption, and pandemic "
            "aftershocks are forcing companies to rethink just-in-time logistics. "
            "Proposes a resilience index framework and benchmarks leading multinationals "
            "against it using publicly available disclosure data."
        ),
        tags=["Supply Chain", "Geopolitics", "Logistics", "Risk"],
    ),
]


def articles_to_dataframe(articles: list[Article]) -> pd.DataFrame:
    """Convert a list of Article objects into a flat pandas DataFrame."""
    return pd.DataFrame([
        {
            "ID":              a.id,
            "Title":           a.title,
            "Author":          a.author,
            "Category":        a.category,
            "Date":            a.date,
            "Word Count":      a.word_count,
            "Reads":           a.reads,
            "Likes":           a.likes,
            "Engagement (%)":  a.engagement_rate,
            "Status":          a.status,
            "Tags":            ", ".join(a.tags),
            "Summary":         a.summary,
        }
        for a in articles
    ])

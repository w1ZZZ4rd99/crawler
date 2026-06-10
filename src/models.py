"""Data models shared across crawler components."""

from dataclasses import asdict, dataclass, field


@dataclass
class PageData:
    """Structured data extracted from a single crawled page."""

    url: str
    title: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    images: list[dict] = field(default_factory=list)
    headings: dict = field(default_factory=dict)
    tables: list = field(default_factory=list)
    lists: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

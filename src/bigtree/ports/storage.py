"""Storage Port interface defining clean I/O contracts."""

from __future__ import annotations

from typing import Any, Protocol

import pandas as pd


class StoragePort(Protocol):
    """Abstract storage port for reading and writing pipeline artifacts."""

    def read_json(self, uri: str) -> dict[str, Any]:
        """Read and parse a JSON document from storage."""
        ...

    def write_json(self, uri: str, data: dict[str, Any]) -> str:
        """Serialize and write a JSON document to storage."""
        ...

    def read_csv(self, uri: str) -> pd.DataFrame:
        """Read a CSV document into a Pandas DataFrame."""
        ...

    def write_csv(self, uri: str, df: pd.DataFrame) -> str:
        """Serialize a Pandas DataFrame to a CSV document in storage."""
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """List all object keys/paths matching a given prefix."""
        ...

"""Hermetic in-memory storage adapter for fast, zero-I/O testing."""

from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd


class InMemoryStorageAdapter:
    """Implements StoragePort entirely in memory with zero filesystem or network dependencies."""

    def __init__(self, initial_files: dict[str, Any] | None = None) -> None:
        self.files: dict[str, str] = {}
        if initial_files:
            for k, v in initial_files.items():
                if isinstance(v, (dict, list)):
                    self.files[k] = json.dumps(v)
                elif isinstance(v, pd.DataFrame):
                    self.files[k] = v.to_csv(index=False)
                else:
                    self.files[k] = str(v)

    def read_json(self, uri: str) -> dict[str, Any]:
        if uri not in self.files:
            raise FileNotFoundError(f"Key not found in memory: {uri}")
        return json.loads(self.files[uri])

    def write_json(self, uri: str, data: dict[str, Any]) -> str:
        self.files[uri] = json.dumps(data, ensure_ascii=False, indent=2)
        return uri

    def read_csv(self, uri: str) -> pd.DataFrame:
        if uri not in self.files:
            raise FileNotFoundError(f"Key not found in memory: {uri}")
        return pd.read_csv(io.StringIO(self.files[uri]))

    def write_csv(self, uri: str, df: pd.DataFrame) -> str:
        self.files[uri] = df.to_csv(index=False)
        return uri

    def list_keys(self, prefix: str) -> list[str]:
        return [k for k in self.files if k.startswith(prefix)]

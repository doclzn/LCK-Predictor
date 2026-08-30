"""Carregamento compartilhado do server.py para a suíte.

Cada teste antes carregava `server.py` do zero via importlib — ~3 s por arquivo,
13 vezes. Aqui ele é carregado uma única vez por sessão. Testes que precisam
escrever no banco pedem a fixture `server_tmpdb`, que aponta `m.DB` para uma
cópia descartável e restaura o original no fim.
"""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def server():
    return _load("lck_server", "server.py")


@pytest.fixture(scope="session")
def riot():
    """riot_feed carregado à parte: alguns testes exercitam o feed sem o app."""
    return _load("riot_feed", "riot_feed.py")


@pytest.fixture
def server_tmpdb(server):
    """Cópia descartável do banco, para testes que escrevem."""
    original = server.DB
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "test.sqlite"
        shutil.copy2(original, tmp)
        server.DB = tmp
        try:
            server.invalidate_draft_reference_caches()
            yield server
        finally:
            server.DB = original
            server.invalidate_draft_reference_caches()

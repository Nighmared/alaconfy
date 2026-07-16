"""Shared fixtures for aconfgen tests."""

from pathlib import Path

import pytest

from alaconfy.model import Document
from alaconfy.parser import parse_document

ROOT = Path(__file__).parents[1]
MAIN_MANPAGE = ROOT / "alacritty.5.scd.txt"
BINDINGS_MANPAGE = ROOT / "alacritty-bindings.5.scd.txt"


@pytest.fixture(scope="session")
def document() -> Document:
    return parse_document(MAIN_MANPAGE, BINDINGS_MANPAGE)

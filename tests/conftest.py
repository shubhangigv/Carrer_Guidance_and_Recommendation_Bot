"""Shared pytest fixtures."""
import pytest

from fake_onet import write_fake_onet


@pytest.fixture
def onet_dir(tmp_path):
    """A temporary folder holding the fake O*NET files."""
    return write_fake_onet(tmp_path)

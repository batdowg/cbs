import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'slow' in item.keywords or 'quarantine' in item.keywords:
            continue
        item.add_marker('full')

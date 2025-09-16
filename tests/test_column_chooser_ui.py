import json

import pytest

pytestmark = pytest.mark.smoke


class ColumnChooserHarness:
    """Simulates the front-end column chooser state machine."""

    def __init__(self, columns, storage, storage_key):
        self.columns = columns
        self.storage = storage
        self.storage_key = storage_key
        self.required_keys = [col["key"] for col in columns if col.get("required")]
        self.optional_keys = [col["key"] for col in columns if not col.get("required")]
        self.optional_default_order = list(self.optional_keys)
        state = self._load_state()
        self.hidden = state["hidden"]
        self.order_override = state["order"]
        self.visible = {
            col["key"]: (col.get("required") or col["key"] not in self.hidden)
            for col in columns
        }
        self.column_order = self._effective_order()

    def _effective_optional_order(self):
        ordered = []
        for key in self.order_override:
            if key in self.optional_keys and key not in ordered:
                ordered.append(key)
        for key in self.optional_default_order:
            if key not in ordered:
                ordered.append(key)
        return ordered

    def _effective_order(self):
        return self.required_keys + self._effective_optional_order()

    def _load_state(self):
        raw = self.storage.get(self.storage_key)
        if not raw:
            return {"order": [], "hidden": set()}
        data = json.loads(raw)
        order = [key for key in data.get("order", []) if key in self.optional_keys]
        hidden = {key for key in data.get("hidden", []) if key in self.optional_keys}
        return {"order": order, "hidden": hidden}

    def toggle(self, key, visible):
        if key in self.required_keys:
            return
        if visible:
            self.hidden.discard(key)
        else:
            self.hidden.add(key)
        self.visible[key] = visible
        self._persist()

    def reset(self):
        self.hidden = set()
        self.order_override = []
        self.visible = {
            col["key"]: col.get("required", False) or col["key"] not in self.hidden
            for col in self.columns
        }
        self.column_order = self._effective_order()
        self._persist()

    def _persist(self):
        payload = json.dumps(
            {
                "order": self.order_override,
                "hidden": sorted(self.hidden),
            }
        )
        self.storage[self.storage_key] = payload
        self.column_order = self._effective_order()
        for key in self.optional_keys:
            self.visible[key] = key not in self.hidden


def test_column_visibility_persists_after_reload():
    columns = [
        {"key": "id", "required": True},
        {"key": "title", "required": True},
        {"key": "client"},
        {"key": "location"},
        {"key": "workshop_type"},
    ]
    storage = {}
    storage_key = "cbs.sessions.columns.42"

    chooser = ColumnChooserHarness(columns, storage, storage_key)
    assert chooser.column_order[:2] == ["id", "title"]
    assert chooser.visible["client"] is True

    chooser.toggle("client", False)
    assert chooser.visible["client"] is False
    persisted = json.loads(storage[storage_key])
    assert persisted["hidden"] == ["client"]

    # Simulate a fresh load that reuses stored preferences.
    new_instance = ColumnChooserHarness(columns, storage, storage_key)
    assert new_instance.visible["client"] is False
    assert new_instance.column_order[:2] == ["id", "title"]

    new_instance.toggle("client", True)
    assert new_instance.visible["client"] is True
    persisted_again = json.loads(storage[storage_key])
    assert persisted_again["hidden"] == []

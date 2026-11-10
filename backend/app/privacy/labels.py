from typing import Literal

Label = Literal["public", "internal", "confidential"]
_RANK: dict[Label, int] = {"public": 0, "internal": 1, "confidential": 2}


def highest_label(*labels: Label) -> Label:
    if not labels:
        return "public"
    return max(labels, key=lambda label: _RANK[label])


def derived_label(*source_labels: Label) -> Label:
    return highest_label(*source_labels)

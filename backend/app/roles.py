from enum import Enum


class Role(str, Enum):
    """Closed role enum. Adding a role is a contract change."""

    NURSE = "nurse"
    PHYSICIAN = "physician"
    PHARMACIST = "pharmacist"

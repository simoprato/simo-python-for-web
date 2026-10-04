"""Categorie di classifica FITP (semplificate) dalla 4.NC alla 2.1.

Ogni categoria è rappresentata da un indice intero: più alto = più forte.
"""

CATEGORIES = [
    "4.NC", "4.6", "4.5", "4.4", "4.3", "4.2", "4.1",
    "3.5", "3.4", "3.3", "3.2", "3.1",
    "2.8", "2.7", "2.6", "2.5", "2.4", "2.3", "2.2", "2.1",
]
MAX_IDX = len(CATEGORIES) - 1


def label(idx):
    return CATEGORIES[max(0, min(MAX_IDX, idx))]


def index(name):
    return CATEGORIES.index(name)


def group(idx):
    """Gruppo di categoria: 2ª, 3ª o 4ª."""
    return int(label(idx)[0])


def clamp(idx):
    return max(0, min(MAX_IDX, idx))

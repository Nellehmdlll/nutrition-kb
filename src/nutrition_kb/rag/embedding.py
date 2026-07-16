"""Modele d'embedding et ses conventions -- point d'entree UNIQUE.

Les modeles e5 (intfloat/*) exigent de prefixer chaque texte par "query: "
(cote recherche) ou "passage: " (cote document a indexer) : sans ce prefixe,
la qualite de recherche degrade fortement -- documente par les auteurs du
modele. Cette convention vit ICI, pas recopiee dans embed_chunks.py et une
future recherche : un prefixe oublie ou incoherent entre les deux serait un
bug silencieux (aucune erreur, juste une recherche moins bonne).
"""

EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


def encode_passages(model, texts, batch_size: int = 64):
    """Encode des CHUNKS (documents a indexer) -- prefixe 'passage: '."""
    prefixed = [_PASSAGE_PREFIX + t for t in texts]
    return model.encode(prefixed, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)


def encode_query(model, text: str):
    """Encode UNE requete de recherche -- prefixe 'query: '."""
    return model.encode(_QUERY_PREFIX + text, normalize_embeddings=True)

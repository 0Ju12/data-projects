"""Offline character n-gram baseline; public API also accepts pretrained vectors."""
import hashlib
import re
import unicodedata
import numpy as np

ENCODER = "signed-char-ngram-v1"


def encode(text, dim=512):
    text = " ".join(unicodedata.normalize("NFKC", text).lower().split())
    result = np.zeros(dim, dtype=np.float32)
    for word in re.findall(r"\w+", text):
        padded = "^" + word + "$"
        for n in (2, 3):
            for i in range(len(padded) - n + 1):
                token = padded[i:i+n].encode("utf-8")
                digest = hashlib.blake2s(token, digest_size=8).digest()
                result[int.from_bytes(digest[:4], "little") % dim] += 1 if digest[4] & 1 else -1
    if not result.any():
        raise ValueError("text contains no indexable tokens")
    return result

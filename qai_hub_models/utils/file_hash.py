# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import hashlib
import os

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB chunks


def hash_file(
    path: str | os.PathLike,
    hasher: hashlib._Hash | None = None,
    read_chunk_size=DEFAULT_CHUNK_SIZE,
) -> hashlib._Hash:
    """
    Updated the given hash with the data in the given file.

    Parameters
    ----------
    path
        File path

    hasher
        Hash object to update. If not provided, a md5 hash is created.

    read_chunk_size
        The file is read and hash updated in small memory chunks, so we don't load the entire file to memory at once.
        This is the chunk size in bytes,

    Returns
    -------
    hasher
        Updated hasher object.
    """
    hasher = hasher or hashlib.md5()
    with open(path, "rb") as f1:
        while True:
            chunk = f1.read(read_chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher


def file_hashes_are_identical(
    path1: str | os.PathLike,
    path2: str | os.PathLike,
    read_chunk_size=DEFAULT_CHUNK_SIZE,
) -> bool:
    """
    Compare the MD5 hashes of two model files.

    Parameters
    ----------
    path1
        File path 1

    path2
        File path 2

    read_chunk_size
        The file is read and hash updated in small memory chunks, so we don't load the entire file to memory at once.
        This is the chunk size in bytes,

    Returns
    -------
    bool
        True if the MD5 hashes of the two model files are the same, False otherwise.
    """
    return (
        hash_file(path1, read_chunk_size=read_chunk_size).digest()
        == hash_file(path2, read_chunk_size=read_chunk_size).digest()
    )

"""C++ symbol demangling utilities."""

from __future__ import annotations

import re
import subprocess


def demangle_cpp(mangled: str) -> str:
    """Demangle a C++ symbol using c++filt.

    Args:
        mangled: Mangled C++ symbol name

    Returns:
        Demangled name, or original if demangling fails
    """
    if not mangled:
        return mangled

    # Skip if doesn't look mangled (no _Z prefix for Itanium ABI)
    if not mangled.startswith("_Z") and not mangled.startswith("__Z"):
        return mangled

    try:
        result = subprocess.run(
            ["c++filt", "-n", mangled],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return mangled


def demangle_cpp_batch(mangled_names: list[str]) -> dict[str, str]:
    """Demangle multiple C++ symbols efficiently.

    Args:
        mangled_names: List of mangled symbol names

    Returns:
        Dictionary mapping mangled names to demangled names
    """
    if not mangled_names:
        return {}

    # Filter to only mangled names
    to_demangle = [n for n in mangled_names if n.startswith("_Z") or n.startswith("__Z")]

    if not to_demangle:
        return {n: n for n in mangled_names}

    result = {n: n for n in mangled_names}

    try:
        proc = subprocess.run(
            ["c++filt", "-n"],
            input="\n".join(to_demangle),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            demangled = proc.stdout.strip().split("\n")
            for mangled, dem in zip(to_demangle, demangled, strict=False):
                if dem:
                    result[mangled] = dem
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return result


def simplify_cpp_signature(demangled: str, max_length: int = 80) -> str:
    """Simplify a demangled C++ signature for display.

    Args:
        demangled: Demangled function signature
        max_length: Maximum length before truncation

    Returns:
        Simplified signature
    """
    if not demangled:
        return demangled

    # Remove return type if present (before first space before function name)
    # Remove template parameters for brevity
    simplified = demangled

    # Remove std:: prefix
    simplified = simplified.replace("std::", "")

    # Simplify common types
    simplified = simplified.replace(
        "basic_string<char, char_traits<char>, allocator<char>>", "string"
    )
    simplified = simplified.replace("basic_string<char>", "string")

    # Remove allocator stuff
    simplified = re.sub(r", allocator<[^>]+>", "", simplified)

    # Truncate if too long
    if len(simplified) > max_length:
        simplified = simplified[:max_length - 3] + "..."

    return simplified

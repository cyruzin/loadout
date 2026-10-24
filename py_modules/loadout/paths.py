"""Token expansion and containment for paths that come from data files."""
from __future__ import annotations

from pathlib import Path

TOKENS = ("{prefix}", "{install_dir}", "{appid}")
ROOT_TOKENS = ("{prefix}/", "{install_dir}/")


def expand(template: str, ctx: dict[str, str]) -> str:
    # Plain replace on purpose: never str.format() with untrusted strings.
    for t in TOKENS:
        template = template.replace(t, ctx[t.strip("{}")])
    if "{" in template or "}" in template:
        raise ValueError("unknown token")
    if "\x00" in template:
        raise ValueError("NUL byte in path")
    return template


def safe_path(template: str, ctx: dict[str, str], allowed_roots: list[Path]) -> Path:
    """Expanded, symlink-resolved path that must stay inside one of the allowed roots."""
    p = Path(expand(template, ctx)).resolve()
    if not any(p.is_relative_to(r.resolve()) for r in allowed_roots):
        raise PermissionError(f"outside the allowed area: {p}")
    return p

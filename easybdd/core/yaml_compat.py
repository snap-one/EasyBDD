"""YAML compatibility shims.

PyYAML follows the YAML 1.1 spec, where unquoted ``on``/``off``/``yes``/``no``
(in any case) resolve to booleans. That's a footgun for test authors writing
steps like ``text: ON`` to verify a toggle's on-screen label — they silently
get the Python bool ``True`` instead of the string ``"ON"``. YAML 1.2 dropped
those aliases and kept only ``true``/``false``; this patch brings PyYAML's
default loaders in line with that behavior.
"""

import yaml

_PATCHED = False


def patch_yaml_bool_resolver() -> None:
    """Stop PyYAML from treating on/off/yes/no as booleans; true/false still work."""
    global _PATCHED
    if _PATCHED:
        return
    resolvers = yaml.resolver.Resolver.yaml_implicit_resolvers
    for first_char in "yYnNoO":
        resolvers[first_char] = [
            (tag, regexp)
            for tag, regexp in resolvers.get(first_char, [])
            if tag != "tag:yaml.org,2002:bool"
        ]
    _PATCHED = True

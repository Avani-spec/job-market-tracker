"""Skill extraction from posting text with NLTK tokenisation + n-gram lookup.

Tokens are produced with an NLTK ``RegexpTokenizer`` whose pattern keeps
technology names intact (``c++``, ``c#``, ``.net``, ``node.js``, ``ci/cd``).
Every 1-3-gram is looked up in an alias index built from ``skills.yaml``.
"""
from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml
from nltk.tokenize import RegexpTokenizer
from nltk.util import everygrams

TAXONOMY = Path(__file__).with_name("skills.yaml")
# words, optionally with internal . or - and trailing + or #, or a leading dot.
# "/" splits tokens ("Python/Django"); "ci/cd" still matches as the bigram (ci, cd)
TOKENIZER = RegexpTokenizer(r"\.?[A-Za-z0-9]+(?:[.\-][A-Za-z0-9]+)*[+#]*")
# after these words "Go"/"C"/"R" are almost certainly not the language
NOT_LANG_AFTER = {"to", "live", "ahead", "through", "level", "suite", "corp", "series"}


@lru_cache(maxsize=4)
def load_taxonomy(path: str = str(TAXONOMY)):
    data = yaml.safe_load(Path(path).read_text())
    ci, cs, cats = {}, {}, {}
    for skill, spec in data.items():
        cats[skill] = spec.get("category", "other")
        target = cs if spec.get("case_sensitive") else ci
        for alias in spec.get("aliases", []) + [skill]:
            key = tuple(TOKENIZER.tokenize(alias if spec.get("case_sensitive") else alias.lower()))
            if key:
                target[key] = skill
    return ci, cs, cats


def extract_skills(text: str, taxonomy: str = str(TAXONOMY)) -> Counter:
    ci, cs, _ = load_taxonomy(taxonomy)
    raw = TOKENIZER.tokenize(text)
    low = [t.lower() for t in raw]
    found = Counter()
    for n in (3, 2, 1):
        for i in range(len(raw) - n + 1):
            key_l = tuple(low[i:i + n])
            if key_l in ci:
                found[ci[key_l]] += 1
                continue
            key = tuple(raw[i:i + n])
            if key in cs:
                nxt = low[i + n] if i + n < len(low) else ""
                if nxt in NOT_LANG_AFTER:
                    continue
                # single capital letters need a list-like neighbour ("C, C++", "R/Python")
                if n == 1 and len(key[0]) == 1 and not _list_context(raw, i):
                    continue
                found[cs[key]] += 1
    # "React Native" also contains "React": keep both only if React appears alone too
    if found.get("React Native") and found.get("React", 0) <= found["React Native"]:
        del found["React"]
    return found


def _list_context(tokens, i) -> bool:
    window = {t.lower() for t in tokens[max(0, i - 2): i + 3]}
    return bool(window & {"python", "c++", "java", "rust", "matlab", "sql", "julia", "go", "golang", "fortran"})


def skills_set(text: str) -> set[str]:
    return set(extract_skills(text))


def category_of(skill: str) -> str:
    return load_taxonomy()[2].get(skill, "other")


ROLE_PATTERNS = [
    ("ML / AI", r"\b(machine learning|ml|ai|deep learning|research scientist|applied scientist|llm)\b"),
    ("Data", r"\b(data (engineer|scientist|analyst)|analytics|bi developer)\b"),
    ("DevOps / SRE", r"\b(devops|sre|site reliability|platform|infrastructure|cloud engineer)\b"),
    ("Mobile", r"\b(ios|android|mobile)\b"),
    ("Frontend", r"\b(front[- ]?end|ui engineer|react developer)\b"),
    ("Backend", r"\b(back[- ]?end|api|server)\b"),
    ("Full-stack", r"\b(full[- ]?stack)\b"),
    ("Security", r"\b(security|appsec|infosec)\b"),
    ("Management", r"\b(manager|head of|director|vp|cto)\b"),
]


def classify_role(title: str) -> str:
    t = title.lower()
    for role, pat in ROLE_PATTERNS:
        if re.search(pat, t):
            return role
    return "Software (general)" if re.search(r"engineer|developer|programmer", t) else "Other"

"""
DESK Skill System & Conditional Skill Loader.

Implements Firstmate-style conditional skill indexing and lazy loading for
electronics engineering agents, keeping agent contexts focused and lean.
Pure standard library implementation with zero external dependencies.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Skill:
    """Represents a discovered and parsed engineering skill."""
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    authoritative_pipeline: str = "M0"
    replay_safety: str = "SAFE_READ"
    path: Optional[Path] = None
    body: str = ""

    def matches(self, text: str) -> int:
        """
        Calculates a match score for a given prompt or instruction text.
        Returns a score >= 0 (0 means no match).
        """
        text_lower = text.lower()
        score = 0

        # Exact skill name mentioned
        if self.name.lower() in text_lower:
            score += 10

        # Token match on name words
        name_words = re.findall(r"\w+", self.name.lower())
        for nw in name_words:
            if nw in text_lower:
                score += 3

        # Match triggers
        for trig in self.triggers:
            trig_clean = trig.lower().strip()
            if trig_clean:
                # Direct substring match
                if trig_clean in text_lower:
                    score += 5
                # Regex match if pattern contains metacharacters
                elif any(c in trig_clean for c in r".*+?[]{}()^$"):
                    try:
                        if re.search(trig_clean, text_lower):
                            score += 5
                    except re.error:
                        pass

        return score


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parses YAML frontmatter from markdown content using pure Python standard library.
    Handles key-value pairs, nested lists, and simple nested dictionaries.
    """
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}, content

    frontmatter_raw = content[3:end_idx].strip()
    body = content[end_idx + 4:].strip()

    metadata: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[str]] = None
    current_dict: Optional[Dict[str, Any]] = None

    lines = frontmatter_raw.splitlines()
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue

        # Check for list item under current key
        if line.startswith("  - ") or line.startswith("    - "):
            val = line.split("- ", 1)[1].strip().strip('"\'')
            if current_list is not None:
                current_list.append(val)
            continue

        # Check for key-value pair under current dict (indented)
        if (line.startswith("  ") or line.startswith("    ")) and ":" in line and not line.startswith("  - "):
            k, v = line.strip().split(":", 1)
            k = k.strip()
            v = v.strip().strip('"\'')
            if current_dict is not None:
                current_dict[k] = v
            continue

        # Top-level key
        if ":" in line_stripped:
            # Flush previous list/dict
            if current_key and current_list is not None:
                metadata[current_key] = current_list
                current_list = None
            elif current_key and current_dict is not None:
                metadata[current_key] = current_dict
                current_dict = None

            k, v = line_stripped.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"\'')

            if not v:
                # Possible start of a list or nested dict
                current_key = k
                # Peek or default to list/dict based on next context
                # For safety, initialize both empty until first child seen
                current_list = []
                current_dict = {}
            else:
                current_key = None
                metadata[k] = v

    # Flush tail
    if current_key and current_list:
        metadata[current_key] = current_list
    elif current_key and current_dict:
        metadata[current_key] = current_dict

    return metadata, body


class SkillRegistry:
    """
    Central registry and conditional loader for DESK engineering skills.
    Discovers skills from `.agents/skills/` or a custom root directory.
    """

    def __init__(self, root_dir: Optional[Path | str] = None) -> None:
        if root_dir is None:
            # Default to repo root / .agents / skills
            repo_root = Path(__file__).resolve().parent.parent
            self.root_dir = repo_root / ".agents" / "skills"
        else:
            self.root_dir = Path(root_dir)

        self._skills: Dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        """Scans root_dir and loads all available skills."""
        self._skills.clear()
        if not self.root_dir.is_dir():
            return

        for skill_dir in self.root_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)
                name = metadata.get("name", skill_dir.name)
                description = metadata.get("description", "")
                triggers = metadata.get("triggers", [])
                if isinstance(triggers, str):
                    triggers = [triggers]

                inputs = metadata.get("inputs", {})
                outputs = metadata.get("outputs", {})
                pipeline = metadata.get("authoritative_pipeline", "M0")
                safety = metadata.get("replay_safety", "SAFE_READ")

                skill = Skill(
                    name=name,
                    description=description,
                    triggers=triggers,
                    inputs=inputs if isinstance(inputs, dict) else {},
                    outputs=outputs if isinstance(outputs, dict) else {},
                    authoritative_pipeline=pipeline,
                    replay_safety=safety,
                    path=skill_file,
                    body=body,
                )
                self._skills[name] = skill
            except Exception:
                # Silently skip malformed skill files to prevent loader crashes
                pass

    @property
    def skills(self) -> Dict[str, Skill]:
        """Returns map of all registered skills."""
        return self._skills

    def get_skill(self, name: str) -> Optional[Skill]:
        """Retrieves a skill by name."""
        return self._skills.get(name)

    def match_skills(self, text: str, threshold: int = 1) -> List[Tuple[Skill, int]]:
        """
        Matches an instruction or query text against all registered skills.
        Returns a list of (Skill, score) tuples sorted by descending score.
        """
        results: List[Tuple[Skill, int]] = []
        for skill in self._skills.values():
            # Exclude skill-index from standard matching unless explicitly requested
            if skill.name == "skill-index" and "index" not in text.lower():
                continue
            score = skill.matches(text)
            if score >= threshold:
                results.append((skill, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_skill_context(self, text: str, max_skills: int = 1) -> str:
        """
        Generates a concise markdown context injection containing only the
        highest-scoring skill procedural instructions for the active prompt.
        """
        matches = self.match_skills(text)
        if not matches:
            return ""

        selected = matches[:max_skills]
        chunks = []
        for skill, score in selected:
            chunks.append(
                f"### Active Skill: `{skill.name}` (Pipeline: {skill.authoritative_pipeline})\n"
                f"*{skill.description}*\n\n"
                f"{skill.body}\n"
            )
        return "\n---\n".join(chunks)


# Module-level default singleton registry
_DEFAULT_REGISTRY: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Returns or initializes the singleton skill registry."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = SkillRegistry()
    return _DEFAULT_REGISTRY

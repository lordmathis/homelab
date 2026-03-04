"""
Skills Toolset Plugin - Read and update skill prompts
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agentkit.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

FRONTMATTER_DELIMITER = "---"


def _parse_skill_file(content: str) -> tuple[dict, str]:
    """Split YAML frontmatter and markdown body. Returns (frontmatter_dict, body)."""
    if not content.startswith(FRONTMATTER_DELIMITER):
        return {}, content

    parts = content.split(FRONTMATTER_DELIMITER, 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, parts[2].lstrip("\n")


def _serialize_skill_file(frontmatter: dict, body: str) -> str:
    """Reconstruct a skill file from frontmatter dict and markdown body."""
    if not frontmatter:
        return body
    fm_str = yaml.dump(frontmatter, default_flow_style=False).rstrip()
    return f"{FRONTMATTER_DELIMITER}\n{fm_str}\n{FRONTMATTER_DELIMITER}\n\n{body}"


class SkillsTool(ToolSetHandler):

    def __init__(self, name: str = "skills"):
        super().__init__(name)
        self._skills_dir: Optional[Path] = None

    async def initialize(self) -> None:
        await super().initialize()
        skills_dir = os.environ.get("SKILLS_DIR", "/app/plugins/skills")
        self._skills_dir = Path(skills_dir)
        if not self._skills_dir.exists():
            logger.warning(f"Skills directory not found: {self._skills_dir}")
        else:
            logger.info(f"Skills directory: {self._skills_dir}")

    @tool(
        description="List all available skills with their names and descriptions",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    async def list_skills(self) -> Dict[str, Any]:
        if not self._skills_dir or not self._skills_dir.exists():
            return {"status": "error", "error": f"Skills directory not found: {self._skills_dir}"}

        skills: List[Dict[str, Any]] = []
        for skill_dir in sorted(self._skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                continue

            content = skill_md.read_text(encoding="utf-8")
            frontmatter, body = _parse_skill_file(content)

            # Extract first H1 heading as title, first non-empty paragraph as description
            title = skill_dir.name
            description = ""
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("# ") and title == skill_dir.name:
                    title = line.lstrip("# ").strip()
                elif line and not line.startswith("#") and not description:
                    description = line
                if title != skill_dir.name and description:
                    break

            skills.append({
                "name": skill_dir.name,
                "title": title,
                "description": description,
                "required_tool_servers": frontmatter.get("required_tool_servers", []),
                "path": str(skill_md)
            })

        return {"status": "success", "count": len(skills), "skills": skills}

    @tool(
        description="Read the full content of a skill's SKILL.md file",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill directory (e.g. 'anki', 'workout')"
                }
            },
            "required": ["skill_name"]
        }
    )
    async def read_skill(self, skill_name: str) -> Dict[str, Any]:
        skill_md = self._resolve_skill_path(skill_name)
        if skill_md is None:
            return {"status": "error", "error": f"Skill '{skill_name}' not found"}

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_skill_file(content)

        return {
            "status": "success",
            "skill_name": skill_name,
            "frontmatter": frontmatter,
            "body": body,
            "raw": content
        }

    @tool(
        description=(
            "Update the markdown body of a skill's SKILL.md file. "
            "The YAML frontmatter (required_tool_servers etc.) is preserved unless explicitly overridden. "
            "Use this after reviewing a conversation to improve a skill's prompt. "
            "If the skill doesn't exist, it will be created."
        ),
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name of the skill directory (e.g. 'anki', 'workout')"
                },
                "body": {
                    "type": "string",
                    "description": "The new markdown body content (everything after the frontmatter)"
                },
                "frontmatter": {
                    "type": "object",
                    "description": "Optional: override frontmatter fields (e.g. required_tool_servers). Omit to preserve existing."
                }
            },
            "required": ["skill_name", "body"]
        }
    )
    async def update_skill(
        self,
        skill_name: str,
        body: str,
        frontmatter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self._skills_dir:
            return {"status": "error", "error": f"Skills directory not configured"}

        skill_name = Path(skill_name).name
        skill_dir = self._skills_dir / skill_name
        skill_md = skill_dir / "SKILL.md"

        is_new = False
        if not skill_md.exists():
            is_new = True
            skill_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created skill directory: {skill_dir}")

        existing_content = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""
        existing_frontmatter, _ = _parse_skill_file(existing_content)

        merged_frontmatter = (existing_frontmatter or {}).copy()
        if frontmatter:
            merged_frontmatter.update(frontmatter)

        new_content = _serialize_skill_file(merged_frontmatter, body)
        skill_md.write_text(new_content, encoding="utf-8")

        action = "Created" if is_new else "Updated"
        logger.info(f"{action} skill '{skill_name}' at {skill_md}")
        return {
            "status": "success",
            "skill_name": skill_name,
            "path": str(skill_md),
            "message": f"Skill '{skill_name}' {action.lower()} successfully"
        }

    def _resolve_skill_path(self, skill_name: str) -> Optional[Path]:
        """Return the SKILL.md Path for a given skill name, or None if not found."""
        if not self._skills_dir:
            return None
        # Sanitize: prevent path traversal
        skill_name = Path(skill_name).name
        skill_md = self._skills_dir / skill_name / "SKILL.md"
        return skill_md if skill_md.exists() else None

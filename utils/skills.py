import yaml
from pathlib import Path

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"

# 按照分隔符--- 切字符串
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 SKILL.md 中的 YAML frontmatter。返回 (meta, body)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2].strip()

def _scan_skills(SKILL_REGISTRY:dict):
    """扫描 skills/ 目录，用 name/description/content 填充 SKILL_REGISTRY。"""
    if not SKILLS_DIR.exists():
        return
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
            SKILL_REGISTRY[name] = {"name": name, "description": desc, "content": raw}

def list_skills(SKILL_REGISTRY:dict) -> str: #根据SKILL_REGISTRY列出每个skill的name和描述,然后在build_system函数注入提示词
    """列出所有 skills（name + 单行 description）。"""
    if not SKILL_REGISTRY:
        return "(no skills found)"
    return "\n".join(f"- **{s['name']}**: {s['description']}" for s in SKILL_REGISTRY.values())

# s07：SYSTEM 包含 skill catalog（便宜——只有名称和描述）
def build_system(SKILL_REGISTRY) -> str:
    """启动时注入 skill catalog，构建 SYSTEM prompt。"""
    catalog = list_skills(SKILL_REGISTRY)
    return (
        f"You are a coding agent at {WORKDIR}. "
        f"Skills available:\n{catalog}\n"
        "Use load_skill to get full details when needed."
    )

SKILL_REGISTRY: dict[str, dict] = {}
_scan_skills(SKILL_REGISTRY)
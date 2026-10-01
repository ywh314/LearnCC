import re
from pathlib import Path
WORKDIR = Path.cwd()

# ═══════════════════════════════════════════════════════════
# s03 新增：三道门 Permission Pipeline
# ═══════════════════════════════════════════════════════════

# Gate 1：硬拒绝列表 —— 永远禁止
DENY_LIST = [
    # 原有 Linux 指令。
    "rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda",
    # Windows / PowerShell：磁盘、启动配置、注册表删除和关机操作。
    "format ", "diskpart", "bcdedit", "reg delete",
    "Clear-Disk", "Format-Volume", "Remove-Partition",
    "Stop-Computer", "Restart-Computer",
]

def check_deny_list(command: str) -> str | None:
    command = command.lower()
    for pattern in DENY_LIST:
        if pattern.lower() in command:
            return f"Blocked: '{pattern}' is on the deny list"
    return None


# Gate 2：规则匹配 —— 依赖 context 的检查
def is_destructive_command(command: str) -> bool:
    command = command.lower()
    # 保留原来的 Linux 审批规则。
    if any(kw in command for kw in ["rm ", "> /etc/", "chmod 777"]):
        return True
    # Windows 删除命令及 PowerShell 别名；匹配大小写、空格或 /s 等参数。
    if re.search(r"(?<![\w-])(?:del|erase|rmdir|rd|remove-item|ri)(?![\w-])", command):
        return True
    # shell 也可能通过 Python 删除文件或目录。
    return any(kw in command for kw in ["shutil.rmtree", "os.remove", "os.unlink", ".unlink("])


PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
     "message": "Writing outside workspace"},
    {"tools": ["bash"],
     "check": lambda args: is_destructive_command(args.get("command", "")),
     "message": "Potentially destructive command"},
]

def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


# Gate 3：用户审批 —— 规则匹配后等待确认
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m⚠  {reason}\033[0m")
    print(f"   Tool: {tool_name}({args})")
    choice = input("   Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# Pipeline：三道门串联
def check_permission(block) -> bool:
    if block.name == "bash":
        reason = check_deny_list(block.input.get("command", ""))
        if reason:
            print(f"\n\033[31m⛔ {reason}\033[0m")
            return False
    reason = check_rules(block.name, block.input)
    if reason:
        decision = ask_user(block.name, block.input, reason)
        if decision == "deny":
            return False
    return True

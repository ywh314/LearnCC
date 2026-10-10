import os
from anthropic import Anthropic
from dotenv import load_dotenv

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.tools import run_bash, run_read, run_write, run_edit, run_glob,load_skill
from utils.hooks import register_hook,trigger_hooks,permission_hook, log_hook, large_output_hook, context_inject_hook, summary_hook
from utils.skills import SKILL_REGISTRY,build_system
from utils.compact import tool_result_budget,snip_compact,micro_compact,compact_history,reactive_compact
from utils.compact import estimate_size,CONTEXT_LIMIT

load_dotenv(override=True)
client = Anthropic(base_url= os.getenv("ANTHROPIC_BASE_URL"))
Model = os.getenv("MODEL_ID")

#---------------SKILL注入提示词----------------------
System = build_system(SKILL_REGISTRY)

# TOOL注册input_schema写法，type，properties,required
TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "load_skill", "description": "Load the full content of a skill by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "compact", "description": "Summarize earlier conversation to free context space.",
     "input_schema": {"type": "object", "properties": {"focus": {"type": "string"}}}},
]
TOOL_HANDLERS = {"bash":run_bash,
                 "read_file":run_read,
                 "write_file":run_write,
                 "edit_file":run_edit,
                 "glob":run_glob,
                 "load_skill":load_skill}

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)

MAX_REACTIVE_RETRIES = 1 # 最大重试次数

def agent_loop(messages: list):
    reactive_retries = 0
    while True:
        # L1:硬压缩，保留头尾(只关注消息数量)-snip_compact

        # L2和L3主要针对tool_result压缩
        # L2:关注每条消息大小micro_compact,针对较大的工具调用结果替换为占位符，并保留最近几条工具调用结果完整
        # L3:snip_compact

        # BUG：L2和L3存在冲突，对于较大的tool_result再L3中会持久化存储，并且记录地址；但是L2中又将较长tool_result完全替换掉
        messages[:] = tool_result_budget(messages)    # L3: persist large results first
        messages[:] = snip_compact(messages)          # L1: trim middle
        messages[:] = micro_compact(messages)         # L2: old result placeholders

        # compact_history已经压缩一遍，后面在判断是否还超出范围
        if estimate_size(messages) > CONTEXT_LIMIT:
            print("[auto compact]")
            messages[:] = compact_history(messages)
        try:
            response = client.messages.create(
                model=Model, messages = messages,system = System,
                tools= TOOLS,max_tokens=8000)
            reactive_retries = 0  # reset on successful API call
        except Exception as e:
            if ("prompt_too_long" in str(e).lower() or "too many tokens" in str(e).lower()) and reactive_retries < MAX_REACTIVE_RETRIES:
                print("[reactive compact]")
                messages[:] = reactive_compact(messages)
                reactive_retries += 1
                continue
            raise

        messages.append({"role":"assistant","content":response.content})

        if response.stop_reason != "tool_use":
            force = trigger_hooks("Stop", messages)
            if force: #暂时并未实现summary功能
                messages.append({"role": "user", "content": force})
                continue
            return
        
        # 工具调用情况：
        results = []
        for block in response.content:
            if block.type != "tool_use":continue

            # s08：设置compact工具，让LLM自主选择压缩
            if block.name == "compact":
                messages[:] = compact_history(messages)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": "[Compacted. Conversation history has been summarized.]"})
                messages.append({"role": "user", "content": results})
                break  # end current turn, start fresh with compacted context
            
            block_reason = trigger_hooks("PreToolUse",block)

            if block_reason:  # 检查权限，若不通过则阻止执行
                results.append({
                "type":"tool_result",
                "tool_use_id":block.id,
                "content":str(block_reason)})
                continue

            # block.input: 按照每个工具input_schema写好的输入字典
            handler = TOOL_HANDLERS[block.name]
            output = handler(**block.input) #自动将字典参数解包传入函数 
            
            trigger_hooks("PostToolUse", block,output)

            # 调用结果的字段参数名也有要求
            results.append({
                "type":"tool_result",
                "tool_use_id":block.id,
                "content":output})

        messages.append({"role":"user","content":results})


if __name__ == "__main__":

    history = []
    while True:
        query = input("\033[36ms01 >> \033[0m")
        if query.strip().lower() in ("q","quit","exit",""):
            break

        trigger_hooks("UserPromptSubmit", query) #在query到达LLM前的hook,当前是打印工作目录
        history.append({"role":"user","content":query})
        agent_loop(history)

        response_content = history[-1]["content"]
        if isinstance(response_content,list):
            for block in response_content:
                if getattr(block,"type",None) == "text":
                    print(block.text)
        print()

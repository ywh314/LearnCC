import os
from anthropic import Anthropic
from dotenv import load_dotenv

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.tools import *
from utils.hooks import *

load_dotenv(override=True)
client = Anthropic(base_url= os.getenv("ANTHROPIC_BASE_URL"))
Model = os.getenv("MODEL_ID")
System = (
    f"You are a coding agent at {WORKDIR}. "
    "Before starting any multi-step task, use todo_write to plan your steps. "
    "Update status as you go."
)

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
    {"name": "todo_write", "description": "Create and manage a task list for your current coding session.",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
]
TOOL_HANDLERS = {"bash":run_bash,
                 "read_file":run_read,
                 "write_file":run_write,
                 "edit_file":run_edit,
                 "glob":run_glob,
                 "todo_write":run_todo_write
}

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)

def agent_loop(messages: list):
    
    while True:
        response = client.messages.create(
            model=Model, messages = messages,system = System,
            tools= TOOLS,max_tokens=8000,extra_body = {"thinking": {"type": "disabled"}})
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
            if block.type != "tool_use":
                continue
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
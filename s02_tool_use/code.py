import os
from anthropic import Anthropic
from dotenv import load_dotenv

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.tools import run_bash, run_read, run_write, run_edit, run_glob
            
load_dotenv(override=True)
client = Anthropic(base_url= os.getenv("ANTHROPIC_BASE_URL"))
Model = os.getenv("MODEL_ID")
System = f"你好，你是coding agent，叫做codex，项目目录位于{os.getcwd()},代码放在当前目录中"

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
]

TOOL_HANDLERS = {"bash":run_bash,
                 "read_file":run_read,
                 "write_file":run_write,
                 "edit_file":run_edit,
                 "glob":run_glob}

def Agent_loop(Message:list):
    
    while True:
        response = client.messages.create(
            model=Model, messages = Message,system = System,
            tools= TOOLS,max_tokens=8000,extra_body = {"thinking": {"type": "disabled"}})
        Message.append({"role":"assistant","content":response.content})
        if response.stop_reason != "tool_use":
            return 
        # 工具调用情况：
        results = []
        for block in response.content:
            if block.type == "tool_use":
                # block.input: 按照每个工具input_schema写好的输入字典
                handler = TOOL_HANDLERS[block.name]

                print(f"\033[33m$ {block.input}\033[0m") #高亮打印输入参数
                output = handler(**block.input) #自动将字典参数解包传入函数 
                
                # 调用结果的字段参数名也有要求
                results.append({
                    "type":"tool_result",
                    "tool_use_id":block.id,
                    "content":output})

        Message.append({"role":"user","content":results})


if __name__ == "__main__":

    history = []
    while True:
        query = input("\033[36ms01 >> \033[0m")

        history.append({"role":"user","content":query})

        Agent_loop(history)
        response_content = history[-1]["content"]

        if isinstance(response_content,list):
            for block in response_content:
                if getattr(block,"type",None) == "text":
                    print(block.text)
        print()
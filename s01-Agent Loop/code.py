from email import message
from re import A
import subprocess
import os
import anthropic

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import Tool
from regex import T

load_dotenv(override=True)

client = Anthropic(base_url= os.getenv("ANTHROPIC_BASE_URL"))
Model = os.getenv("MODEL_ID")
System = f"你好，你是coding agent，叫做codex，项目目录位于{os.getcwd()},代码放在当前目录中"

Tools = []

tool1 = {
    "name":"bash",
    "description":"执行cmd中的一些指令",
    "input_schema":{
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
        }
Tools.append(tool1)

def run_bash(command:str):
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "dangerous command"
    try:
        """
        - `shell=True`：通过系统 shell 执行命令。
        - `cwd=...`：设置命令运行目录。
        - `capture_output=True`：捕获 stdout 和 stderr。
        - `text=True`：让输出以字符串形式返回。
        - `timeout=120`：最多等待 120 秒。
        - `check` 默认是 `False`：即使命令失败，通常也会返回结果，不自动抛异常
        """
        r = subprocess.run(command,shell=True,capture_output=True,
                       text=True,timeout=30)
        output = (r.stdout + r.stderr).strip()
        return output[: 50000] if output else "no output"
    
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


def Agent_loop(Message:list):
    
    while True:
        response = client.messages.create(
            model=Model, messages = Message,system = System,
            tools= Tools,max_tokens=8000,extra_body = {"thinking": {"type": "disabled"}})
        Message.append({"role":"assistant","content":response.content})
        if response.stop_reason != "tool_use":
            return 
        # 工具调用情况：
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\033[33m$ {block.input['command']}\033[0m") #高亮打印cmd指令
                output = run_bash(block.input["command"])
            
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
import os
from anthropic import Anthropic
from dotenv import load_dotenv

from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.hooks import trigger_hooks   # import后 自动将hook注册进入
from utils.skills import SKILL_REGISTRY,list_skills
from utils.compact import tool_result_budget,snip_compact,micro_compact,compact_history,reactive_compact
from utils.compact import estimate_size,CONTEXT_LIMIT
from utils.registry import TOOLS,TOOL_HANDLERS
from utils.memory import load_memories, extract_memories,consolidate_memories, read_memory_index

load_dotenv(override=True)
client = Anthropic(base_url= os.getenv("ANTHROPIC_BASE_URL"))
Model = os.getenv("MODEL_ID")

WORKDIR = Path.cwd()

# 使用新的build_system
def build_system() -> str:
    catalog = list_skills(SKILL_REGISTRY)

    index = read_memory_index()
    memories_section = f"\n\nMemories available:\n{index}" if index else ""
    return (
        f"You are a coding agent at {WORKDIR}."
        f"{memories_section}\n"
        "Relevant memories are injected below. Respect user preferences from memory.\n"
        "When the user says 'remember' or expresses a clear preference, extract it as a memory.\n\n"
        f"Skills available:\n{catalog}\n"
        "Use load_skill to get full details when needed."
    )

MAX_REACTIVE_RETRIES = 1 # 最大重试次数

def agent_loop(messages: list):
    reactive_retries = 0

    # s09：把相关 memory 内容注入当前 user turn
    memories_content = load_memories(messages)
    memory_turn = len(messages) - 1 if messages and isinstance(messages[-1].get("content"), str) else None
    # s09：每个 user turn 构建一次 system；loop 返回后更新 memory
    
    system = build_system() #将MEMORY.md注入系统提示词
    while True:
        # 有点类似于copy,似乎只是浅拷贝，message变化，pre_compress也会变化
        pre_compress = [m if isinstance(m, dict) else {"role": m.get("role",""),
            "content": str(m.get("content",""))} for m in messages]
        
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
            request_messages = messages
            if memories_content and memory_turn is not None and memory_turn < len(messages):
                # 字典覆盖写法！
                request_messages = messages.copy()
                request_messages[memory_turn] = {
                    **messages[memory_turn],
                    "content": memories_content + "\n\n" + messages[memory_turn]["content"],
                }
                
            response = client.messages.create(
                model=Model, messages = request_messages,system = system,
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
            
            # loop结束前，将记忆存储
            extract_memories(pre_compress)
            consolidate_memories()
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
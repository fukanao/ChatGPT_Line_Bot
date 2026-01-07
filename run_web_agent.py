import asyncio
from agents import Agent, Runner, WebSearchTool, ItemHelpers
import os
from dotenv import load_dotenv


load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from openai.types.responses import ResponseTextDeltaEvent

researcher = Agent(
    name="Researcher",
    instructions="質問の答えが確信できるまで何度でも検索して要約してください",
    tools=[WebSearchTool()],
    model="gpt-4.1",
)

async def main():
    result = Runner.run_streamed(researcher, input="次世代 GPT-5 の公式発表日は？")

    async for ev in result.stream_events():

        # ① LLM からのテキスト増分
        if ev.type == "raw_response_event" and isinstance(ev.data, ResponseTextDeltaEvent):
            if ev.data.delta:
                print(ev.data.delta, end="", flush=True)

        # ② ツール呼び出し
        elif ev.type == "run_item_stream_event":
            item = ev.item

            # 2-A: ツール呼び出し開始
            if item.type == "tool_call_item":
                payload = item.raw_item.model_dump(exclude_none=True)
                tool_name = item.raw_item.__class__.__name__
                print(f"\n🔧 {tool_name} → {payload}")

            # 2-B ツール呼び出し結果
            elif item.type == "tool_call_output_item":
                # WebSearchTool の場合、output は List[SearchResult]
                for i, r in enumerate(item.output, 1):
                    print(f"   {i}. {r.url}")

    print("\n=== 完了 ===\n", result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
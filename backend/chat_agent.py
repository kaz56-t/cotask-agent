"""
LangGraphによる対話フローの実装
ユーザーの曖昧な指示に対し、AIが質問を返す対話システム
要件定義フロー: 推測を入れずに要件を定義し、不明点を確認
"""
from typing import TypedDict, Annotated, Literal, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
import os
import json
import re
from dotenv import load_dotenv
from langfuse_config import get_langfuse_handler

# .envファイルを読み込む（ローカル開発環境用のフォールバック）
# docker-compose.ymlでenv_fileを指定している場合は、環境変数として既に利用可能
load_dotenv()


class ChatState(TypedDict):
    """チャット状態の定義"""
    messages: Annotated[list[BaseMessage], lambda x, y: x + y if y else x]
    requirements_defined: bool  # 要件が確定したかどうか
    requirements_summary: str  # 要件の要約


# システムプロンプト: 要件定義のための指示
REQUIREMENTS_SYSTEM_PROMPT = """あなたはタスクの要件定義を支援するAIアシスタントです。

あなたの役割:
1. ユーザーが入力した情報をもとに、推測を入れずにタスクの要件を定義する
2. 不明点があれば、明確な質問をして確認する
3. 要件が確定したら、「要件確定」と明示する

重要なルール:
- 推測や仮定を入れず、ユーザーが明示的に述べた情報のみを使用する
- 不明点がある場合は、具体的な質問をする
- 要件が確定したら、最後に「[要件確定]」というマーカーを含める
- 要件が確定していない場合は、次に確認すべき点を明確に示す

応答フォーマット:
- 要件の要約を最初に示す（ユーザーが明示した情報のみ）
- 不明点があれば質問する
- 要件が確定したら「[要件確定]」を含める"""


def create_chat_agent():
    """LangGraphによるチャットエージェントの作成"""
    
    # OpenAI APIキーの確認
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY環境変数が設定されていません")
    
    # LLMの初期化（コールバックは実行時に渡す）
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        api_key=api_key
    )
    
    def chat_node(state: ChatState) -> ChatState:
        """チャットノード: ユーザーメッセージに対してAIが応答を生成"""
        messages = state["messages"]
        requirements_defined = state.get("requirements_defined", False)
        requirements_summary = state.get("requirements_summary", "")
        
        # 最後のメッセージがユーザーからのものか確認
        if messages and isinstance(messages[-1], HumanMessage):
            # システムプロンプトを最初に追加（まだ追加されていない場合）
            messages_with_system = messages
            if not messages or not isinstance(messages[0], SystemMessage):
                messages_with_system = [SystemMessage(content=REQUIREMENTS_SYSTEM_PROMPT)] + list(messages)
            
            # LLMにメッセージを送信（コールバックはLLMインスタンスに設定済み）
            response = llm.invoke(messages_with_system)
            messages = list(messages) + [response]
            
            # 要件確定の判定
            response_content = response.content if hasattr(response, 'content') else str(response)
            requirements_defined = "[要件確定]" in response_content or "要件確定" in response_content
            
            # 要件の要約を抽出（最初の段落を要約として使用）
            if requirements_defined:
                # 要件確定の場合、要約を抽出
                lines = response_content.split('\n')
                summary_lines = []
                for line in lines:
                    if line.strip() and not line.strip().startswith('['):
                        summary_lines.append(line.strip())
                        if len(summary_lines) >= 3:  # 最初の3行を要約として使用
                            break
                requirements_summary = '\n'.join(summary_lines) if summary_lines else response_content[:200]
            
            return {
                "messages": messages,
                "requirements_defined": requirements_defined,
                "requirements_summary": requirements_summary
            }
        
        return {
            "messages": messages,
            "requirements_defined": requirements_defined,
            "requirements_summary": requirements_summary
        }
    
    # ステートグラフの構築
    workflow = StateGraph(ChatState)
    workflow.add_node("chat", chat_node)
    workflow.set_entry_point("chat")
    workflow.add_edge("chat", END)
    
    # コンパイル
    app = workflow.compile()
    return app


def format_messages_for_langgraph(messages: list[dict]) -> list[BaseMessage]:
    """データベースから取得したメッセージをLangGraph形式に変換"""
    formatted = []
    for msg in messages:
        if msg["role"] == "user":
            formatted.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            formatted.append(AIMessage(content=msg["content"]))
    return formatted

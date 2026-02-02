"""
LangGraphのワークフローグラフを画像として出力するスクリプト
"""
import os
from pathlib import Path
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, END

# 簡易的な状態定義（実際のAgentStateと同じ構造）
class AgentState(TypedDict):
    messages: Annotated[list, lambda x, y: x + y]
    task_id: str
    task_name: str
    task_description: str
    runtime_output_path: str
    current_agent: str
    iteration_count: int
    max_iterations: int


def create_sample_workflow():
    """サンプルワークフローを作成（実際のagents.pyと同じ構造）"""
    def architect_node(state: AgentState) -> AgentState:
        return state
    
    def executor_node(state: AgentState) -> AgentState:
        return state
    
    def should_continue(state: AgentState) -> Literal["architect", "__end__"]:
        if state.get("current_agent") == "end":
            return "__end__"
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 2)
        if iteration_count >= max_iterations:
            return "__end__"
        if state.get("current_agent") == "end":
            return "__end__"
        else:
            return "architect"
    
    # グラフの構築
    workflow = StateGraph(AgentState)
    workflow.add_node("architect", architect_node)
    workflow.add_node("executor", executor_node)
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", "executor")
    workflow.add_conditional_edges(
        "executor",
        should_continue,
        {
            "architect": "architect",
            "__end__": END
        }
    )
    
    return workflow.compile()


def generate_graph_images():
    """グラフ画像を生成"""
    output_dir = Path(__file__).parent.parent / "docs" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Creating Task Agent workflow graph...")
    app = create_sample_workflow()
    
    try:
        # Mermaid形式で出力
        graph = app.get_graph()
        
        # Mermaidコードを取得
        mermaid_code = graph.draw_mermaid()
        mermaid_file = output_dir / "task_agent_workflow.mmd"
        with open(mermaid_file, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"✓ Mermaid file saved: {mermaid_file}")
        
        # PNG画像として出力（可能な場合）
        try:
            png_data = graph.draw_mermaid_png()
            if png_data:
                png_file = output_dir / "task_agent_workflow.png"
                with open(png_file, "wb") as f:
                    f.write(png_data)
                print(f"✓ PNG image saved: {png_file}")
        except Exception as e:
            print(f"⚠ PNG generation not available: {e}")
            print("  You can convert the Mermaid file using online tools or mermaid-cli")
        
        # ASCII形式でも出力
        try:
            ascii_diagram = graph.draw_ascii()
            ascii_file = output_dir / "task_agent_workflow.txt"
            with open(ascii_file, "w", encoding="utf-8") as f:
                f.write(ascii_diagram)
            print(f"✓ ASCII diagram saved: {ascii_file}")
        except Exception as e:
            print(f"⚠ ASCII generation not available: {e}")
            
    except Exception as e:
        print(f"Error generating graph: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    generate_graph_images()

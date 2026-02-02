"use client";

import { useState, useEffect } from "react";
import TaskSidebar from "@/components/TaskSidebar";
import TaskForm from "@/components/TaskForm";
import { api } from "@/lib/api";
import { Plus, Send, Loader2 } from "lucide-react";

export default function Home() {
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Array<{
    id: number;
    role: string;
    content: string;
    timestamp: string;
    requirements_defined?: boolean;
    requirements_summary?: string;
  }>>([]);
  const [loading, setLoading] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [requirementsDefined, setRequirementsDefined] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [sendOnEnter, setSendOnEnter] = useState<boolean>(() => {
    // localStorageから設定を読み込む（デフォルトはfalse = Shift+Enterで送信）
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sendOnEnter');
      return saved === 'true';
    }
    return false;
  });

  // タスクが選択されたときにチャット履歴を読み込む
  useEffect(() => {
    if (selectedTaskId) {
      loadChatHistory();
    } else {
      setMessages([]);
    }
  }, [selectedTaskId]);

  const loadChatHistory = async (taskId?: string | null) => {
    const targetTaskId = taskId || selectedTaskId;
    if (!targetTaskId) return;

    setLoadingChat(true);
    try {
      const [chatSession, task] = await Promise.all([
        api.getTaskChat(targetTaskId),
        api.getTask(targetTaskId)
      ]);
      setMessages(chatSession.messages);
      setTaskStatus(task.status);
      
      // 最後のメッセージで要件が確定しているか確認
      const lastMessage = chatSession.messages[chatSession.messages.length - 1];
      if (lastMessage && lastMessage.role === "assistant") {
        const isDefined = lastMessage.content.includes("[要件確定]") || 
                         lastMessage.content.includes("要件確定");
        setRequirementsDefined(isDefined);
      } else {
        setRequirementsDefined(false);
      }
    } catch (error) {
      console.error("Failed to load chat history:", error);
      setMessages([]);
      setRequirementsDefined(false);
      setTaskStatus(null);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleTaskSelect = (taskId: string) => {
    setSelectedTaskId(taskId);
    setShowTaskForm(false);
  };

  const handleTaskCreated = async () => {
    setShowTaskForm(false);
    // サイドバーが自動的に更新される（ポーリングのため）
    // 少し待ってから最新のタスクを選択（新しく作成されたタスクを自動選択）
    setTimeout(async () => {
      try {
        const response = await api.getTasks({ limit: 1 });
        if (response.tasks.length > 0) {
          const newTask = response.tasks[0];
          setSelectedTaskId(newTask.id);
          // チャット履歴を読み込む（新しく作成されたタスクのIDを渡す）
          await loadChatHistory(newTask.id);
        }
      } catch (error) {
        console.error("Failed to select new task:", error);
      }
    }, 500);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!message.trim() || !selectedTaskId || loading) return;

    const userMessage = message.trim();
    setMessage("");
    setLoading(true);

    // ユーザーメッセージを即座に表示
    const tempUserMessage = {
      id: Date.now(),
      role: "user",
      content: userMessage,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    try {
      const response = await api.sendTaskMessage(selectedTaskId, userMessage);
      
      // 要件確定フラグを更新
      if (response.requirements_defined) {
        setRequirementsDefined(true);
      }
      
      // 応答を追加
      setMessages((prev) => {
        // 一時的なユーザーメッセージを実際のメッセージに置き換え
        const filtered = prev.filter((msg) => msg.id !== tempUserMessage.id);
        return [
          ...filtered,
          {
            id: response.id,
            role: response.role,
            content: response.content,
            timestamp: response.timestamp,
            requirements_defined: response.requirements_defined,
            requirements_summary: response.requirements_summary,
          },
        ];
      });
    } catch (error) {
      console.error("Failed to send message:", error);
      // エラーメッセージを表示
      setMessages((prev) => {
        const filtered = prev.filter((msg) => msg.id !== tempUserMessage.id);
        return [
          ...filtered,
          {
            id: Date.now(),
            role: "assistant",
            content: "エラー: メッセージの送信に失敗しました",
            timestamp: new Date().toISOString(),
          },
        ];
      });
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteTask = async () => {
    if (!selectedTaskId || executing) return;

    setExecuting(true);
    try {
      const result = await api.executeTask(selectedTaskId);
      
      // タスクステータスを更新
      setTaskStatus("running");
      
      // 実行開始のメッセージを表示
      const executeMessage = {
        id: Date.now(),
        role: "assistant",
        content: result.message,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, executeMessage]);
      
      // タスクステータスをポーリングして更新
      const pollTaskStatus = async () => {
        try {
          const task = await api.getTask(selectedTaskId);
          setTaskStatus(task.status);
          if (task.status === "running") {
            // まだ実行中の場合は2秒後に再度確認
            setTimeout(pollTaskStatus, 2000);
          }
        } catch (error) {
          console.error("Failed to poll task status:", error);
        }
      };
      setTimeout(pollTaskStatus, 2000);
    } catch (error) {
      console.error("Failed to execute task:", error);
      alert("タスクの実行に失敗しました。要件が確定しているか確認してください。");
    } finally {
      setExecuting(false);
    }
  };

  const handleSendModeChange = (mode: boolean) => {
    setSendOnEnter(mode);
    if (typeof window !== 'undefined') {
      localStorage.setItem('sendOnEnter', mode.toString());
    }
  };

  return (
    <div className="flex h-screen bg-zinc-50 dark:bg-black">
      {/* サイドバー */}
      <div className="w-80 flex-shrink-0 border-r border-zinc-200 dark:border-zinc-800">
        <TaskSidebar
          selectedTaskId={selectedTaskId}
          onTaskSelect={handleTaskSelect}
        />
      </div>

      {/* メインコンテンツエリア */}
      <div className="flex-1 flex flex-col">
        {/* ページ上部ヘッダー */}
        <div className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <div className="p-4">
            {showTaskForm ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">新しいタスクを作成</h3>
                  <button
                    onClick={() => setShowTaskForm(false)}
                    className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  >
                    ✕
                  </button>
                </div>
                <TaskForm onTaskCreated={handleTaskCreated} />
              </div>
            ) : (
              <button
                onClick={() => setShowTaskForm(true)}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                新しいタスク
              </button>
            )}
          </div>
        </div>

        {selectedTaskId ? (
          <>
            {/* チャット履歴 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {loadingChat ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-8 h-8 animate-spin text-zinc-400" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex items-center justify-center h-full text-zinc-500 dark:text-zinc-400">
                  メッセージがありません。メッセージを送信して会話を始めましょう。
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${
                      msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg px-4 py-2 ${
                        msg.role === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-50"
                      }`}
                    >
                      <p className="text-sm whitespace-pre-wrap break-words">
                        {msg.content}
                      </p>
                      <p className="text-xs mt-1 opacity-70">
                        {new Date(msg.timestamp).toLocaleTimeString("ja-JP", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* 要件確定時の実行ボタン */}
            {requirementsDefined && taskStatus !== "running" && taskStatus !== "completed" && taskStatus !== "failed" && (
              <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-green-50 dark:bg-green-900/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-1">
                      要件が確定しました
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400">
                      タスクを実行できます
                    </p>
                  </div>
                  <button
                    onClick={handleExecuteTask}
                    disabled={executing}
                    className="px-6 py-2 rounded-lg bg-green-600 text-white font-medium hover:bg-green-700 disabled:bg-zinc-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                  >
                    {executing ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        実行中...
                      </>
                    ) : (
                      "タスクを実行"
                    )}
                  </button>
                </div>
              </div>
            )}
            
            {/* 実行中の表示 */}
            {taskStatus === "running" && (
              <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-blue-50 dark:bg-blue-900/20">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    タスクを実行中です...
                  </p>
                </div>
              </div>
            )}

            {/* メッセージ入力欄 */}
            <div className="border-t border-zinc-200 dark:border-zinc-800 p-4">
              {/* 送信方法の切り替え */}
              <div className="mb-2 flex items-center justify-end gap-2">
                <span className="text-xs text-zinc-500 dark:text-zinc-400">送信方法:</span>
                <div className="flex gap-1 bg-zinc-100 dark:bg-zinc-800 rounded-md p-1">
                  <button
                    type="button"
                    onClick={() => handleSendModeChange(false)}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      !sendOnEnter
                        ? "bg-blue-600 text-white"
                        : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
                    }`}
                  >
                    Shift+Enter
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSendModeChange(true)}
                    className={`px-2 py-1 text-xs rounded transition-colors ${
                      sendOnEnter
                        ? "bg-blue-600 text-white"
                        : "text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200"
                    }`}
                  >
                    Enter
                  </button>
                </div>
              </div>
              <form onSubmit={handleSubmit} className="flex gap-2">
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (sendOnEnter) {
                      // Enterで送信、Shift+Enterで改行
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (message.trim() && !loading) {
                          handleSubmit(e as any);
                        }
                      }
                    } else {
                      // Shift+Enterで送信、Enterだけでは改行
                      if (e.key === "Enter" && e.shiftKey) {
                        e.preventDefault();
                        if (message.trim() && !loading) {
                          handleSubmit(e as any);
                        }
                      }
                    }
                  }}
                  placeholder={sendOnEnter ? "メッセージを入力... (Enterで送信、Shift+Enterで改行)" : "メッセージを入力... (Shift+Enterで送信、Enterで改行)"}
                  rows={3}
                  className="flex-1 px-4 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-black dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !message.trim()}
                  className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:bg-zinc-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2 self-end"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  送信
                </button>
              </form>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-zinc-500 dark:text-zinc-400">
            <div className="text-center">
              <p className="text-lg mb-2">タスクを選択してください</p>
              <p className="text-sm">
                左側のサイドバーからタスクを選択するか、上部の「新しいタスク」ボタンからタスクを作成してください。
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

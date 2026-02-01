"use client";

import { useEffect, useState } from "react";
import { Clock, CheckCircle2, XCircle, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Task, TaskStatus } from "@/lib/types";

interface TaskSidebarProps {
  selectedTaskId: string | null;
  onTaskSelect: (taskId: string) => void;
}

const STATUS_CONFIG: Record<TaskStatus, { icon: React.ReactNode; color: string; label: string }> = {
  pending: {
    icon: <Clock className="w-4 h-4" />,
    color: "text-yellow-600 dark:text-yellow-400",
    label: "定義中",
  },
  running: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    color: "text-blue-600 dark:text-blue-400",
    label: "実行中",
  },
  completed: {
    icon: <CheckCircle2 className="w-4 h-4" />,
    color: "text-green-600 dark:text-green-400",
    label: "完了",
  },
  failed: {
    icon: <XCircle className="w-4 h-4" />,
    color: "text-red-600 dark:text-red-400",
    label: "失敗",
  },
  cancelled: {
    icon: <AlertCircle className="w-4 h-4" />,
    color: "text-gray-600 dark:text-gray-400",
    label: "キャンセル",
  },
};

export default function TaskSidebar({
  selectedTaskId,
  onTaskSelect,
}: TaskSidebarProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = async () => {
    try {
      const response = await api.getTasks({ limit: 100 });
      setTasks(response.tasks);
    } catch (err) {
      console.error("Failed to fetch tasks:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    // ポーリングでタスク一覧を更新（3秒ごと）
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, []);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString("ja-JP", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getProgress = (task: Task): number => {
    if (task.status === "completed") return 100;
    if (task.status === "failed" || task.status === "cancelled") return 0;
    if (task.status === "running" && task.started_at) {
      // 簡易的な進捗計算（実際の進捗はログから取得する必要がある）
      return 50;
    }
    return 0;
  };

  return (
    <div className="h-full flex flex-col bg-zinc-50 dark:bg-zinc-900 border-r border-zinc-200 dark:border-zinc-800">
      <div className="p-4 border-b border-zinc-200 dark:border-zinc-800">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">タスク</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {tasks.length} 件のタスク
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-zinc-500 dark:text-zinc-400">読み込み中...</div>
        ) : tasks.length === 0 ? (
          <div className="p-4 text-center text-zinc-500 dark:text-zinc-400">
            タスクがありません。新しいタスクを作成してください。
          </div>
        ) : (
          <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {tasks.map((task) => {
              const statusConfig = STATUS_CONFIG[task.status];
              const progress = getProgress(task);
              const isSelected = selectedTaskId === task.id;

              return (
                <button
                  key={task.id}
                  onClick={() => onTaskSelect(task.id)}
                  className={`w-full p-4 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors ${
                    isSelected
                      ? "bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500"
                      : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="font-medium text-sm truncate flex-1 text-zinc-900 dark:text-zinc-50">
                      {task.name}
                    </h3>
                    <div className={`flex-shrink-0 ${statusConfig.color}`}>
                      {statusConfig.icon}
                    </div>
                  </div>

                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2 line-clamp-2">
                    {task.description}
                  </p>

                  {task.status === "running" && (
                    <div className="mb-2">
                      <div className="w-full bg-zinc-200 dark:bg-zinc-700 rounded-full h-1.5">
                        <div
                          className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                        {progress}%
                      </p>
                    </div>
                  )}

                  <div className="flex items-center justify-between text-xs text-zinc-400 dark:text-zinc-500">
                    <span>{formatDate(task.created_at)}</span>
                    <span>{statusConfig.label}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

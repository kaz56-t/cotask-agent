"use client";

import { useEffect, useState } from "react";
import { Clock, CheckCircle2, XCircle, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { t, getLanguage } from "@/lib/i18n";
import type { Task, TaskStatus } from "@/lib/types";

interface TaskSidebarProps {
  selectedTaskId: string | null;
  onTaskSelect: (taskId: string) => void;
}

const getStatusConfig = (status: TaskStatus, translations: ReturnType<typeof t>) => {
  const configs: Record<TaskStatus, { icon: React.ReactNode; color: string; getLabel: () => string }> = {
    pending: {
      icon: <Clock className="w-4 h-4" />,
      color: "text-yellow-600 dark:text-yellow-400",
      getLabel: () => translations.status.defining,
    },
    running: {
      icon: <Loader2 className="w-4 h-4 animate-spin" />,
      color: "text-blue-600 dark:text-blue-400",
      getLabel: () => translations.status.running,
    },
    completed: {
      icon: <CheckCircle2 className="w-4 h-4" />,
      color: "text-green-600 dark:text-green-400",
      getLabel: () => translations.status.completed,
    },
    failed: {
      icon: <XCircle className="w-4 h-4" />,
      color: "text-red-600 dark:text-red-400",
      getLabel: () => translations.status.failed,
    },
    cancelled: {
      icon: <AlertCircle className="w-4 h-4" />,
      color: "text-gray-600 dark:text-gray-400",
      getLabel: () => translations.status.cancelled,
    },
  };
  return configs[status];
};

export default function TaskSidebar({
  selectedTaskId,
  onTaskSelect,
}: TaskSidebarProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [language, setLanguage] = useState(getLanguage());

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
    // Update task list with polling (every 3 seconds)
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, []);

  // Listen for language changes
  useEffect(() => {
    const handleLanguageChange = () => {
      setLanguage(getLanguage());
    };
    window.addEventListener('languagechange', handleLanguageChange);
    return () => window.removeEventListener('languagechange', handleLanguageChange);
  }, []);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString(language === 'ja' ? "ja-JP" : "en-US", {
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
      // Simple progress calculation (actual progress should be obtained from logs)
      return 50;
    }
    return 0;
  };

  const translations = t();

  return (
    <div className="h-full flex flex-col bg-zinc-50 dark:bg-zinc-900 border-r border-zinc-200 dark:border-zinc-800">
      <div className="p-4 border-b border-zinc-200 dark:border-zinc-800">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{translations.task.tasks}</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {language === 'ja' 
            ? `${tasks.length} ${translations.task.taskCount}`
            : `${tasks.length} ${tasks.length !== 1 ? translations.task.taskCountPlural : translations.task.taskCount}`
          }
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-zinc-500 dark:text-zinc-400">{translations.common.loading}</div>
        ) : tasks.length === 0 ? (
          <div className="p-4 text-center text-zinc-500 dark:text-zinc-400">
            {translations.task.noTasksMessage}
          </div>
        ) : (
          <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {tasks.map((task) => {
              const statusConfig = getStatusConfig(task.status, translations);
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
                    <span>{statusConfig.getLabel()}</span>
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

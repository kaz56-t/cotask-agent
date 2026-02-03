"use client";

import { useEffect, useState, useRef } from "react";
import {
  Download,
  Trash2,
  XCircle,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Task, TaskLog, Artifact } from "@/lib/types";

interface TaskDetailProps {
  taskId: string | null;
  onTaskDeleted: () => void;
}

export default function TaskDetail({ taskId, onTaskDeleted }: TaskDetailProps) {
  const [task, setTask] = useState<Task | null>(null);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"logs" | "artifacts">("logs");
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchTask = async () => {
    if (!taskId) return;

    try {
      const [taskData, logsData, artifactsData] = await Promise.all([
        api.getTask(taskId),
        api.getTaskLogs(taskId, 0, 1000),
        api.getTaskArtifacts(taskId).catch(() => ({ artifacts: [] })),
      ]);

      setTask(taskData);
      setLogs(logsData);
      setArtifacts(artifactsData.artifacts);
    } catch (err) {
      console.error("Failed to fetch task details:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (taskId) {
      setLoading(true);
      fetchTask();
      // Poll logs for running tasks (every 2 seconds)
      const interval = setInterval(() => {
        if (task?.status === "running") {
          fetchTask();
        }
      }, 2000);
      return () => clearInterval(interval);
    } else {
      setTask(null);
      setLogs([]);
      setArtifacts([]);
    }
  }, [taskId]);

  useEffect(() => {
    // Auto-scroll when logs are updated
    if (activeTab === "logs" && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, activeTab]);

  const handleDelete = async () => {
    if (!taskId || !confirm("Are you sure you want to delete this task?")) {
      return;
    }

    try {
      await api.deleteTask(taskId);
      onTaskDeleted();
    } catch (err) {
      console.error("Failed to delete task:", err);
      alert("Failed to delete task");
    }
  };

  const handleDownload = (artifact: Artifact) => {
    if (!taskId) return;
    const url = api.getArtifactDownloadUrl(taskId, artifact.path);
    window.open(url, "_blank");
  };

  if (!taskId) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        Select a task to view details
      </div>
    );
  }

  if (loading || !task) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  const getStatusIcon = () => {
    switch (task.status) {
      case "completed":
        return <CheckCircle2 className="w-5 h-5 text-green-600" />;
      case "failed":
        return <XCircle className="w-5 h-5 text-red-600" />;
      case "running":
        return <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />;
      case "pending":
        return <Clock className="w-5 h-5 text-yellow-600" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-600" />;
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              {getStatusIcon()}
              <h2 className="text-xl font-semibold">{task.name}</h2>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {task.description}
            </p>
          </div>
          <button
            onClick={handleDelete}
            className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
            title="Delete task"
          >
            <Trash2 className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-gray-400 mt-3">
          <div>
            <span className="font-medium">Model:</span> {task.model_name} ({task.model_provider})
          </div>
          <div>
            <span className="font-medium">Status:</span>{" "}
            <span className="capitalize">{task.status}</span>
          </div>
          {task.started_at && (
            <div>
              <span className="font-medium">Started:</span>{" "}
              {new Date(task.started_at).toLocaleString()}
            </div>
          )}
          {task.completed_at && (
            <div>
              <span className="font-medium">Completed:</span>{" "}
              {new Date(task.completed_at).toLocaleString()}
            </div>
          )}
        </div>

        {task.error_message && (
          <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
            <p className="text-sm text-red-700 dark:text-red-400">
              {task.error_message}
            </p>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 dark:border-gray-800">
        <button
          onClick={() => setActiveTab("logs")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "logs"
              ? "border-b-2 border-blue-500 text-blue-600 dark:text-blue-400"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          }`}
        >
          Logs ({logs.length})
        </button>
        <button
          onClick={() => setActiveTab("artifacts")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "artifacts"
              ? "border-b-2 border-blue-500 text-blue-600 dark:text-blue-400"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          }`}
        >
          Artifacts ({artifacts.length})
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "logs" ? (
          <div className="p-4 space-y-2">
            {logs.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                No logs yet
              </div>
            ) : (
              logs.map((log) => (
                <div
                  key={log.id}
                  className="p-3 bg-gray-50 dark:bg-gray-800 rounded-md"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-gray-600 dark:text-gray-400 capitalize">
                      {log.role}
                    </span>
                    <span className="text-xs text-gray-400">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <pre className="text-sm whitespace-pre-wrap break-words">
                    {log.content}
                  </pre>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        ) : (
          <div className="p-4">
            {artifacts.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                No artifacts yet
              </div>
            ) : (
              <div className="space-y-2">
                {artifacts.map((artifact) => (
                  <div
                    key={artifact.path}
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-md"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">
                        {artifact.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {(artifact.size / 1024).toFixed(2)} KB
                      </p>
                    </div>
                    <button
                      onClick={() => handleDownload(artifact)}
                      className="ml-4 p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                      title="Download artifact"
                    >
                      <Download className="w-5 h-5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

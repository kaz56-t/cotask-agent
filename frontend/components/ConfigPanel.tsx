"use client";

import { useEffect, useState } from "react";
import { Settings, Save, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Config, Stats } from "@/lib/types";

interface ConfigPanelProps {
  onConfigUpdated: () => void;
}

export default function ConfigPanel({ onConfigUpdated }: ConfigPanelProps) {
  const [config, setConfig] = useState<Config | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [maxConcurrent, setMaxConcurrent] = useState(3);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [configData, statsData] = await Promise.all([
        api.getConfig(),
        api.getStats(),
      ]);
      setConfig(configData);
      setStats(statsData);
      setMaxConcurrent(configData.max_concurrent_tasks);
    } catch (err) {
      console.error("Failed to fetch config:", err);
      setError(err instanceof Error ? err.message : "Failed to load config");
    }
  };

  useEffect(() => {
    fetchData();
    // 統計情報を定期的に更新（5秒ごと）
    const interval = setInterval(() => {
      api.getStats().then(setStats).catch(console.error);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      const updated = await api.updateConfig(maxConcurrent);
      setConfig(updated);
      onConfigUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update config");
    } finally {
      setIsSaving(false);
    }
  };

  if (!config || !stats) {
    return (
      <div className="p-4 text-center text-gray-500">
        <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
        Loading configuration...
      </div>
    );
  }

  return (
    <div className="p-4 space-y-6">
      <div className="flex items-center gap-2 mb-4">
        <Settings className="w-5 h-5" />
        <h2 className="text-lg font-semibold">Configuration</h2>
      </div>

      {/* 並列実行数設定 */}
      <div>
        <label
          htmlFor="maxConcurrent"
          className="block text-sm font-medium mb-2"
        >
          Max Concurrent Tasks
        </label>
        <div className="flex items-center gap-4">
          <input
            id="maxConcurrent"
            type="number"
            min="1"
            max="10"
            value={maxConcurrent}
            onChange={(e) => setMaxConcurrent(parseInt(e.target.value) || 1)}
            className="w-24 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-600"
          />
          <button
            onClick={handleSave}
            disabled={isSaving || maxConcurrent === config.max_concurrent_tasks}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Current: {config.max_concurrent_tasks} tasks
        </p>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {/* 統計情報 */}
      <div className="border-t border-gray-200 dark:border-gray-800 pt-4">
        <h3 className="text-sm font-medium mb-3">System Statistics</h3>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-500 dark:text-gray-400">Total Tasks:</span>
            <span className="ml-2 font-medium">{stats.total_tasks}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Running:</span>
            <span className="ml-2 font-medium text-blue-600 dark:text-blue-400">
              {stats.running_tasks}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Pending:</span>
            <span className="ml-2 font-medium text-yellow-600 dark:text-yellow-400">
              {stats.pending_tasks}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Completed:</span>
            <span className="ml-2 font-medium text-green-600 dark:text-green-400">
              {stats.completed_tasks}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Failed:</span>
            <span className="ml-2 font-medium text-red-600 dark:text-red-400">
              {stats.failed_tasks}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Queue Size:</span>
            <span className="ml-2 font-medium">{stats.queue_size}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

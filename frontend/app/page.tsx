"use client";

import { useState, useEffect } from "react";
import TaskSidebar from "@/components/TaskSidebar";
import TaskForm from "@/components/TaskForm";
import SettingsModal from "@/components/SettingsModal";
import { api } from "@/lib/api";
import { Plus, Send, Loader2, Download, Settings } from "lucide-react";
import { t, getLanguage, setLanguage } from "@/lib/i18n";
import type { Artifact } from "@/lib/types";

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
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [language, setLanguageState] = useState(getLanguage());
  const [sendOnEnter, setSendOnEnter] = useState<boolean>(() => {
    // Load settings from localStorage (default is false = send with Shift+Enter)
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('sendOnEnter');
      return saved === 'true';
    }
    return false;
  });

  // Listen for language changes
  useEffect(() => {
    const handleLanguageChange = () => {
      setLanguageState(getLanguage());
    };
    window.addEventListener('languagechange', handleLanguageChange);
    return () => window.removeEventListener('languagechange', handleLanguageChange);
  }, []);

  // Load chat history when task is selected
  useEffect(() => {
    if (selectedTaskId) {
      loadChatHistory();
    } else {
      setMessages([]);
      setArtifacts([]);
    }
  }, [selectedTaskId]);

  // Automatically load artifacts when task status becomes completed
  useEffect(() => {
    if (selectedTaskId && taskStatus === "completed") {
      loadArtifacts(selectedTaskId);
    }
  }, [selectedTaskId, taskStatus]);

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
      
      // Check if requirements are defined in the last message
      const lastMessage = chatSession.messages[chatSession.messages.length - 1];
      if (lastMessage && lastMessage.role === "assistant") {
        const isDefined = lastMessage.content.includes("[要件確定]") || 
                         lastMessage.content.includes("要件確定");
        setRequirementsDefined(isDefined);
      } else {
        setRequirementsDefined(false);
      }
      
      // Load artifacts if task is completed
      if (task.status === "completed") {
        loadArtifacts(targetTaskId);
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

  const loadArtifacts = async (taskId: string) => {
    setLoadingArtifacts(true);
    try {
      const response = await api.getTaskArtifacts(taskId);
      setArtifacts(response.artifacts);
    } catch (error) {
      console.error("Failed to load artifacts:", error);
      setArtifacts([]);
    } finally {
      setLoadingArtifacts(false);
    }
  };

  const handleDownloadArtifact = (artifact: Artifact) => {
    if (!selectedTaskId) return;
    const url = api.getArtifactDownloadUrl(selectedTaskId, artifact.path);
    window.open(url, "_blank");
  };

  const handleTaskSelect = (taskId: string) => {
    setSelectedTaskId(taskId);
    setShowTaskForm(false);
  };

  const handleTaskCreated = async () => {
    setShowTaskForm(false);
    // Sidebar will automatically update (due to polling)
    // Wait a bit then select the latest task (auto-select newly created task)
    setTimeout(async () => {
      try {
        const response = await api.getTasks({ limit: 1 });
        if (response.tasks.length > 0) {
          const newTask = response.tasks[0];
          setSelectedTaskId(newTask.id);
          // Load chat history (pass ID of newly created task)
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

    // Display user message immediately
    const tempUserMessage = {
      id: Date.now(),
      role: "user",
      content: userMessage,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMessage]);

    try {
      const response = await api.sendTaskMessage(selectedTaskId, userMessage);
      
      // Update requirements defined flag
      if (response.requirements_defined) {
        setRequirementsDefined(true);
      }
      
      // Add response
      setMessages((prev) => {
        // Replace temporary user message with actual message
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
      // Display error message
      const translations = t();
      setMessages((prev) => {
        const filtered = prev.filter((msg) => msg.id !== tempUserMessage.id);
        return [
          ...filtered,
          {
            id: Date.now(),
            role: "assistant",
            content: translations.chat.failedToSend,
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
      
      // Update task status
      setTaskStatus("running");
      
      // Display execution start message
      const executeMessage = {
        id: Date.now(),
        role: "assistant",
        content: result.message,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, executeMessage]);
      
      // Poll task status and update
      const pollTaskStatus = async () => {
        try {
          const task = await api.getTask(selectedTaskId);
          const previousStatus = taskStatus;
          setTaskStatus(task.status);
          
          // Load artifacts if task is completed
          if (task.status === "completed" && previousStatus !== "completed") {
            await loadArtifacts(selectedTaskId);
          }
          
          if (task.status === "running") {
            // Check again after 2 seconds if still running
            setTimeout(pollTaskStatus, 2000);
          }
        } catch (error) {
          console.error("Failed to poll task status:", error);
        }
      };
      setTimeout(pollTaskStatus, 2000);
    } catch (error) {
      console.error("Failed to execute task:", error);
      const translations = t();
      alert(translations.chat.failedToExecute);
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

  const translations = t();

  return (
    <div className="flex h-screen bg-zinc-50 dark:bg-black">
      {/* Sidebar */}
      <div className="w-80 flex-shrink-0 border-r border-zinc-200 dark:border-zinc-800">
        <TaskSidebar
          selectedTaskId={selectedTaskId}
          onTaskSelect={handleTaskSelect}
        />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col">
        {/* Page header */}
        <div className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
          <div className="p-4 flex items-center justify-between">
            <div className="flex-1">
              {showTaskForm ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{translations.task.createNewTask}</h3>
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
                  {translations.task.newTask}
                </button>
              )}
            </div>
            <button
              onClick={() => setShowSettingsModal(true)}
              className="ml-4 p-2 text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              title={translations.common.settings}
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>

        {selectedTaskId ? (
          <>
            {/* Chat history */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {loadingChat ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-8 h-8 animate-spin text-zinc-400" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex items-center justify-center h-full text-zinc-500 dark:text-zinc-400">
                  {translations.chat.noMessagesMessage}
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
                        {new Date(msg.timestamp).toLocaleTimeString(language === 'ja' ? "ja-JP" : "en-US", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Execute button when requirements are defined */}
            {requirementsDefined && taskStatus !== "running" && taskStatus !== "completed" && taskStatus !== "failed" && (
              <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-green-50 dark:bg-green-900/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-1">
                      {translations.chat.requirementsDefined}
                    </p>
                    <p className="text-xs text-green-600 dark:text-green-400">
                      {translations.chat.requirementsDefinedMessage}
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
                        {translations.chat.executing}
                      </>
                    ) : (
                      translations.chat.executeTask
                    )}
                  </button>
                </div>
              </div>
            )}
            
            {/* Running status display */}
            {taskStatus === "running" && (
              <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-blue-50 dark:bg-blue-900/20">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    {translations.chat.taskRunning}
                  </p>
                </div>
              </div>
            )}

            {/* Artifacts display when task is completed */}
            {taskStatus === "completed" && (
              <div className="border-t border-zinc-200 dark:border-zinc-800 p-4 bg-green-50 dark:bg-green-900/20">
                <div className="mb-3">
                  <h3 className="text-sm font-semibold text-green-800 dark:text-green-200 mb-1">
                    {translations.chat.taskCompleted}
                  </h3>
                  <p className="text-xs text-green-600 dark:text-green-400">
                    {translations.chat.taskCompletedMessage}
                  </p>
                </div>
                {loadingArtifacts ? (
                  <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-300">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {translations.chat.artifactsLoading}
                  </div>
                ) : artifacts.length > 0 ? (
                  <div className="space-y-2">
                    {artifacts.map((artifact) => (
                      <div
                        key={artifact.path}
                        className="flex items-center justify-between p-3 bg-white dark:bg-zinc-800 rounded-lg border border-green-200 dark:border-green-800"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-sm text-zinc-900 dark:text-zinc-50 truncate">
                            {artifact.name}
                          </p>
                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                            {(artifact.size / 1024).toFixed(2)} KB
                          </p>
                        </div>
                        <button
                          onClick={() => handleDownloadArtifact(artifact)}
                          className="ml-4 p-2 text-green-600 hover:bg-green-100 dark:hover:bg-green-900/30 rounded-md transition-colors flex items-center gap-2"
                          title={translations.common.download}
                        >
                          <Download className="w-4 h-4" />
                          <span className="text-sm">{translations.common.download}</span>
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-green-700 dark:text-green-300">
                    {translations.chat.artifactsNotGenerated}
                  </div>
                )}
              </div>
            )}

            {/* Message input area */}
            <div className="border-t border-zinc-200 dark:border-zinc-800 p-4">
              <form onSubmit={handleSubmit} className="flex gap-2">
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (sendOnEnter) {
                      // Send with Enter, newline with Shift+Enter
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        if (message.trim() && !loading) {
                          handleSubmit(e as any);
                        }
                      }
                    } else {
                      // Send with Shift+Enter, newline with Enter only
                      if (e.key === "Enter" && e.shiftKey) {
                        e.preventDefault();
                        if (message.trim() && !loading) {
                          handleSubmit(e as any);
                        }
                      }
                    }
                  }}
                  placeholder={sendOnEnter ? translations.chat.enterMessagePlaceholder : translations.chat.enterMessagePlaceholderShift}
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
                  {translations.common.send}
                </button>
              </form>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-zinc-500 dark:text-zinc-400">
            <div className="text-center">
              <p className="text-lg mb-2">{translations.task.selectTask}</p>
              <p className="text-sm">
                {translations.task.selectTaskMessage}
              </p>
            </div>
          </div>
        )}
      </div>
      
      {/* Settings Modal */}
      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        sendOnEnter={sendOnEnter}
        onSendModeChange={handleSendModeChange}
      />
    </div>
  );
}

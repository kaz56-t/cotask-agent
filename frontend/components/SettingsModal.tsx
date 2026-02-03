"use client";

import { useState, useEffect } from "react";
import { X, Settings as SettingsIcon } from "lucide-react";
import { getLanguage, setLanguage, type Language } from "@/lib/i18n";
import { t } from "@/lib/i18n";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  sendOnEnter: boolean;
  onSendModeChange: (sendOnEnter: boolean) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  sendOnEnter,
  onSendModeChange,
}: SettingsModalProps) {
  const [language, setLanguageState] = useState<Language>(getLanguage());
  const [localSendOnEnter, setLocalSendOnEnter] = useState(sendOnEnter);

  useEffect(() => {
    if (isOpen) {
      setLanguageState(getLanguage());
      setLocalSendOnEnter(sendOnEnter);
    }
  }, [isOpen, sendOnEnter]);

  const handleLanguageChange = (lang: Language) => {
    setLanguageState(lang);
    setLanguage(lang);
    // Force re-render by reloading translations
    window.dispatchEvent(new Event('languagechange'));
  };

  const handleSendModeChange = (mode: boolean) => {
    setLocalSendOnEnter(mode);
    onSendModeChange(mode);
  };

  const handleClose = () => {
    onClose();
  };

  if (!isOpen) return null;

  const translations = t();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/70">
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow-xl w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <SettingsIcon className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              {translations.settings.title}
            </h2>
          </div>
          <button
            onClick={handleClose}
            className="p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Language Selection */}
          <div>
            <label className="block text-sm font-medium text-zinc-900 dark:text-zinc-50 mb-2">
              {translations.settings.language}
            </label>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
              {translations.settings.languageDescription}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => handleLanguageChange('en')}
                className={`flex-1 px-4 py-2 rounded-md border transition-colors ${
                  language === 'en'
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-700'
                }`}
              >
                English
              </button>
              <button
                onClick={() => handleLanguageChange('ja')}
                className={`flex-1 px-4 py-2 rounded-md border transition-colors ${
                  language === 'ja'
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-700'
                }`}
              >
                日本語
              </button>
            </div>
          </div>

          {/* Send Mode Selection */}
          <div>
            <label className="block text-sm font-medium text-zinc-900 dark:text-zinc-50 mb-2">
              {translations.settings.sendMode}
            </label>
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-3">
              {translations.settings.sendModeDescription}
            </p>
            <div className="space-y-2">
              <button
                onClick={() => handleSendModeChange(true)}
                className={`w-full px-4 py-3 rounded-md border text-left transition-colors ${
                  localSendOnEnter
                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 text-blue-700 dark:text-blue-300'
                    : 'bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-700'
                }`}
              >
                <div className="font-medium mb-1">
                  {translations.settings.sendModeEnter}
                </div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {translations.settings.sendModeEnterDescription}
                </div>
              </button>
              <button
                onClick={() => handleSendModeChange(false)}
                className={`w-full px-4 py-3 rounded-md border text-left transition-colors ${
                  !localSendOnEnter
                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 text-blue-700 dark:text-blue-300'
                    : 'bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-700'
                }`}
              >
                <div className="font-medium mb-1">
                  {translations.settings.sendModeShiftEnter}
                </div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {translations.settings.sendModeShiftEnterDescription}
                </div>
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end p-4 border-t border-zinc-200 dark:border-zinc-800">
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            {translations.common.close}
          </button>
        </div>
      </div>
    </div>
  );
}

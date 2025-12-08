/**
 * End Chat Modal Component
 * Shows when user ends the chat session with option to download AI-generated PDF summary
 */

import { FC, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Message } from '../types';
import { generateChatPDF } from '../services/pdfExportService';
import { generateChatSummary, ChatSummary } from '../services/summaryService';

interface EndChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmEnd: () => void;
  messages: Message[];
  userName: string;
}

export const EndChatModal: FC<EndChatModalProps> = ({
  isOpen,
  onClose,
  onConfirmEnd,
  messages,
  userName,
}) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiSummary, setAiSummary] = useState<ChatSummary | null>(null);
  const [error, setError] = useState('');

  const messageCount = messages.filter(m => m.role !== 'system').length;
  const userMessages = messages.filter(m => m.role === 'user').length;
  const adviserMessages = messages.filter(m => m.role === 'assistant').length;

  // Generate AI summary when modal opens
  const handleGenerateSummary = async () => {
    if (aiSummary) return; // Already generated
    
    setIsGenerating(true);
    setError('');
    
    try {
      const summary = await generateChatSummary(
        messages.filter(m => m.role !== 'system'),
        userName
      );
      
      if (summary.success) {
        setAiSummary(summary);
      } else {
        setError(summary.error || 'Failed to generate summary');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownloadPDF = async () => {
    // Generate summary first if not already done
    let summary = aiSummary;
    if (!summary) {
      setIsGenerating(true);
      try {
        summary = await generateChatSummary(
          messages.filter(m => m.role !== 'system'),
          userName
        );
        setAiSummary(summary);
      } catch {
        // Continue without AI summary
      }
      setIsGenerating(false);
    }

    generateChatPDF({
      userName,
      sessionDate: new Date(),
      messages: messages.filter(m => m.role !== 'system'),
      aiSummary: summary || undefined,
      includeTimestamps: true,
      includeFullConversation: true,
    });
  };

  const handleEndAndDownload = async () => {
    await handleDownloadPDF();
    onConfirmEnd();
  };

  const handleClose = () => {
    // Reset state when closing
    setAiSummary(null);
    setError('');
    onClose();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={handleClose}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden max-h-[90vh] flex flex-col">
              {/* Header */}
              <div className="bg-gradient-to-r from-[#AC2B37] to-[#8B1C26] px-6 py-4 flex-shrink-0">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-white/20 rounded-lg">
                    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">End Chat Session</h2>
                    <p className="text-white/80 text-sm">Generate AI summary & download PDF</p>
                  </div>
                </div>
              </div>

              {/* Content - Scrollable */}
              <div className="px-6 py-5 overflow-y-auto flex-1">
                {/* Stats */}
                <div className="grid grid-cols-3 gap-3 mb-6">
                  <div className="bg-gray-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-gray-800">{messageCount}</div>
                    <div className="text-xs text-gray-500">Messages</div>
                  </div>
                  <div className="bg-blue-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-blue-600">{userMessages}</div>
                    <div className="text-xs text-gray-500">Your Questions</div>
                  </div>
                  <div className="bg-red-50 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-[#AC2B37]">{adviserMessages}</div>
                    <div className="text-xs text-gray-500">Responses</div>
                  </div>
                </div>

                {/* AI Summary Preview */}
                {!aiSummary && !isGenerating && (
                  <div className="bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl p-4 mb-4 border border-purple-100">
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-purple-100 rounded-lg">
                        <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-gray-800 text-sm">AI-Powered Summary</h3>
                        <p className="text-xs text-gray-500 mt-1">
                          Generate a detailed summary with key topics and recommendations using Gemini AI.
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={handleGenerateSummary}
                      className="mt-3 w-full py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      Generate Summary
                    </button>
                  </div>
                )}

                {/* Loading State */}
                {isGenerating && (
                  <div className="bg-gray-50 rounded-xl p-6 mb-4 text-center">
                    <div className="inline-flex items-center justify-center w-12 h-12 bg-purple-100 rounded-full mb-3">
                      <svg className="w-6 h-6 text-purple-600 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    </div>
                    <h3 className="font-semibold text-gray-800 text-sm">Generating AI Summary...</h3>
                    <p className="text-xs text-gray-500 mt-1">
                      Analyzing your conversation with Gemini AI
                    </p>
                  </div>
                )}

                {/* Error State */}
                {error && (
                  <div className="bg-red-50 rounded-xl p-4 mb-4 border border-red-100">
                    <div className="flex items-start gap-2 text-red-600 text-sm">
                      <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>{error}</span>
                    </div>
                    <button
                      onClick={handleGenerateSummary}
                      className="mt-2 text-xs text-red-600 hover:text-red-800 underline"
                    >
                      Try again
                    </button>
                  </div>
                )}

                {/* Summary Preview */}
                {aiSummary && aiSummary.success && (
                  <div className="bg-green-50 rounded-xl p-4 mb-4 border border-green-100">
                    <div className="flex items-center gap-2 mb-3">
                      <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <h3 className="font-semibold text-green-800 text-sm">Summary Generated!</h3>
                    </div>
                    
                    {/* Preview of topics */}
                    {aiSummary.keyTopics.length > 0 && (
                      <div className="mb-3">
                        <p className="text-xs font-medium text-gray-600 mb-1">Key Topics:</p>
                        <div className="flex flex-wrap gap-1">
                          {aiSummary.keyTopics.slice(0, 4).map((topic, i) => (
                            <span key={i} className="text-xs bg-white px-2 py-1 rounded text-gray-700">
                              {topic.length > 25 ? topic.substring(0, 25) + '...' : topic}
                            </span>
                          ))}
                          {aiSummary.keyTopics.length > 4 && (
                            <span className="text-xs text-gray-500 px-2 py-1">
                              +{aiSummary.keyTopics.length - 4} more
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {aiSummary.recommendations.length > 0 && (
                      <p className="text-xs text-gray-600">
                        ✓ {aiSummary.recommendations.length} recommendations included
                      </p>
                    )}
                  </div>
                )}

                {/* Download Option */}
                <div className="bg-gray-50 rounded-xl p-4 mb-4">
                  <div className="flex items-start gap-3">
                    <div className="p-2 bg-[#AC2B37]/10 rounded-lg">
                      <svg className="w-5 h-5 text-[#AC2B37]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <h3 className="font-semibold text-gray-800 text-sm">Download PDF Report</h3>
                      <p className="text-xs text-gray-500 mt-1">
                        {aiSummary ? 'Includes AI summary, key topics, recommendations, and full conversation.' : 'Generate AI summary first for a detailed report, or download conversation only.'}
                      </p>
                    </div>
                  </div>
                  
                  <button
                    onClick={handleDownloadPDF}
                    disabled={isGenerating}
                    className="mt-3 w-full py-2 px-4 bg-white border border-gray-200 hover:border-[#AC2B37] hover:bg-[#AC2B37]/5 text-gray-700 text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    {aiSummary ? 'Download Full Report' : 'Download PDF'}
                  </button>
                </div>

                {/* Warning */}
                <div className="flex items-start gap-2 text-amber-600 bg-amber-50 rounded-lg px-3 py-2 text-xs">
                  <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span>Ending the session will clear your chat history. Download the PDF first if you want to save it.</span>
                </div>
              </div>

              {/* Actions */}
              <div className="px-6 py-4 bg-gray-50 flex gap-3 flex-shrink-0 border-t">
                <button
                  onClick={handleClose}
                  disabled={isGenerating}
                  className="flex-1 py-2.5 px-4 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-medium rounded-lg transition-all disabled:opacity-50"
                >
                  Continue Chat
                </button>
                <button
                  onClick={handleEndAndDownload}
                  disabled={isGenerating}
                  className="flex-1 py-2.5 px-4 bg-[#AC2B37] hover:bg-[#8B1C26] text-white font-medium rounded-lg transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isGenerating ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      <span>Processing...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span>End & Download</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

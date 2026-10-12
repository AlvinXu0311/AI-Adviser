import { FC } from 'react';
import { Message, Role } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User } from 'lucide-react';
import { AgentProcess } from './AgentProcess';
import { motion } from 'framer-motion';

interface MessageBubbleProps {
  message: Message;
  isLast: boolean;
  isStreaming?: boolean;
}

export const MessageBubble: FC<MessageBubbleProps> = ({ message, isLast, isStreaming = false }) => {
  const isUser = message.role === Role.USER;
  const hasSteps = !isUser && !!message.agentSteps && message.agentSteps.length > 0;
  const hasContent = message.content.trim().length > 0;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} group`}
    >
      <div className={`flex max-w-[95%] sm:max-w-[90%] md:max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-2 sm:gap-3`}>
        
        {/* Avatar - hidden on very small screens for user messages */}
        <div className={`flex-shrink-0 w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center shadow-sm mt-1 ${
          isUser ? 'bg-gray-200 hidden sm:flex' : 'bg-wpi-red'
        }`}>
          {isUser ? <User size={16} className="text-gray-600 sm:w-5 sm:h-5" /> : <Bot size={16} className="text-white sm:w-5 sm:h-5" />}
        </div>

        {/* Bubble Content */}
        <div className="flex flex-col space-y-2">
          {/* Sender Name */}
          <span className={`text-xs sm:text-sm font-semibold text-gray-500 ${isUser ? 'text-right' : 'text-left'} px-1`}>
            {isUser ? 'You' : 'Digital Adviser'}
          </span>

          <div className={`
            relative p-3 sm:p-4 rounded-2xl shadow-sm text-xs sm:text-sm leading-relaxed
            ${isUser 
              ? 'bg-wpi-red text-white rounded-tr-none' 
              : 'bg-white text-gray-800 border border-gray-100 rounded-tl-none'
            }
          `}>
             {/* Agent reasoning trace (thoughts + tool calls), shown above the answer */}
             {hasSteps && (
               <div className={hasContent ? 'mb-3' : ''}>
                 <AgentProcess steps={message.agentSteps!} isStreaming={isStreaming} />
               </div>
             )}

             {/* Render Markdown Content */}
             {(hasContent || !hasSteps) && (
             <div className={`markdown-body ${isUser ? 'text-white' : 'text-gray-800'}`}>
                {/* Use a simplified renderer or standard styling */}
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({node, ...props}) => <p className="mb-3 last:mb-0" {...props} />,
                    ul: ({node, ...props}) => <ul className="list-disc ml-4 mb-2" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal ml-4 mb-2" {...props} />,
                    a: ({node, ...props}) => <a className="underline font-semibold hover:opacity-80" {...props} />,
                    strong: ({node, ...props}) => <strong className="font-bold" {...props} />,
                    h1: ({node, ...props}) => <h1 className="text-lg sm:text-2xl font-bold mt-3 sm:mt-4 mb-2" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-base sm:text-xl font-bold mt-3 sm:mt-4 mb-2" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-sm sm:text-lg font-bold mt-2 sm:mt-3 mb-1 sm:mb-2" {...props} />,
                    h4: ({node, ...props}) => <h4 className="text-xs sm:text-base font-bold mt-2 sm:mt-3 mb-1" {...props} />,
                    table: ({node, ...props}) => (
                      <div className="overflow-x-auto my-3 sm:my-4">
                        <table className="min-w-full border-collapse border border-gray-300 text-xs sm:text-sm" {...props} />
                      </div>
                    ),
                    thead: ({node, ...props}) => <thead className="bg-gray-100" {...props} />,
                    tbody: ({node, ...props}) => <tbody {...props} />,
                    tr: ({node, ...props}) => <tr className="border-b border-gray-200" {...props} />,
                    th: ({node, ...props}) => (
                      <th className="px-2 sm:px-4 py-2 sm:py-3 text-left font-semibold text-gray-700 border border-gray-300 bg-gray-50" {...props} />
                    ),
                    td: ({node, ...props}) => (
                      <td className="px-2 sm:px-4 py-2 sm:py-3 text-gray-600 border border-gray-300" {...props} />
                    ),
                    code: ({node, className, children, ...props}) => {
                      const isInline = !className;
                      return isInline ? (
                        <code className="bg-gray-100 text-wpi-red px-1.5 py-0.5 rounded text-sm font-mono" {...props}>{children}</code>
                      ) : (
                        <code className={`block bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono ${className}`} {...props}>{children}</code>
                      );
                    },
                    blockquote: ({node, ...props}) => (
                      <blockquote className="border-l-4 border-wpi-red pl-4 my-3 italic text-gray-600" {...props} />
                    )
                  }}
                >
                  {message.content}
                </ReactMarkdown>
             </div>
             )}

          </div>

          {/* Citations hidden by default - only shown if user explicitly asks for sources */}
          
          <span className={`text-xs text-gray-400 ${isUser ? 'text-right' : 'text-left'} px-1`}>
             {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </motion.div>
  );
};
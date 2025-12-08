import { FC } from 'react';
import { Message, Role } from '../types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, CheckCircle2, Book, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';

interface MessageBubbleProps {
  message: Message;
  isLast: boolean;
}

export const MessageBubble: FC<MessageBubbleProps> = ({ message, isLast }) => {
  const isUser = message.role === Role.USER;

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} group`}
    >
      <div className={`flex max-w-[90%] md:max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-3`}>
        
        {/* Avatar */}
        <div className={`flex-shrink-0 w-14 h-14 rounded-full flex items-center justify-center shadow-sm mt-1 ${
          isUser ? 'bg-gray-200' : 'bg-wpi-red'
        }`}>
          {isUser ? <User size={28} className="text-gray-600" /> : <Bot size={28} className="text-white" />}
        </div>

        {/* Bubble Content */}
        <div className="flex flex-col space-y-2">
          {/* Sender Name */}
          <span className={`text-base font-semibold text-gray-500 ${isUser ? 'text-right' : 'text-left'} px-1`}>
            {isUser ? 'You' : 'Digital Adviser'}
          </span>

          <div className={`
            relative p-6 rounded-2xl shadow-sm text-xl leading-relaxed
            ${isUser 
              ? 'bg-wpi-red text-white rounded-tr-none' 
              : 'bg-white text-gray-800 border border-gray-100 rounded-tl-none'
            }
          `}>
             {/* Render Markdown Content */}
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
                    h1: ({node, ...props}) => <h1 className="text-2xl font-bold mt-4 mb-2" {...props} />,
                    h2: ({node, ...props}) => <h2 className="text-xl font-bold mt-4 mb-2" {...props} />,
                    h3: ({node, ...props}) => <h3 className="text-lg font-bold mt-3 mb-2" {...props} />,
                    h4: ({node, ...props}) => <h4 className="text-base font-bold mt-3 mb-1" {...props} />,
                    table: ({node, ...props}) => (
                      <div className="overflow-x-auto my-4">
                        <table className="min-w-full border-collapse border border-gray-300 text-base" {...props} />
                      </div>
                    ),
                    thead: ({node, ...props}) => <thead className="bg-gray-100" {...props} />,
                    tbody: ({node, ...props}) => <tbody {...props} />,
                    tr: ({node, ...props}) => <tr className="border-b border-gray-200" {...props} />,
                    th: ({node, ...props}) => (
                      <th className="px-4 py-3 text-left font-semibold text-gray-700 border border-gray-300 bg-gray-50" {...props} />
                    ),
                    td: ({node, ...props}) => (
                      <td className="px-4 py-3 text-gray-600 border border-gray-300" {...props} />
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

             {/* Thought Steps (Agentic View) - Only for Assistant */}
             {!isUser && message.thoughtSteps && message.thoughtSteps.length > 0 && (
               <div className="mt-4 pt-4 border-t border-gray-100">
                  <p className="text-sm text-gray-400 font-semibold mb-2 uppercase tracking-wider flex items-center">
                    <CheckCircle2 size={16} className="mr-2 text-green-500" /> 
                    Agent Process
                  </p>
                  <div className="space-y-2">
                    {message.thoughtSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center text-sm text-gray-500 font-mono bg-gray-50 px-3 py-2 rounded">
                        <ArrowRight size={14} className="mr-2 text-gray-300" />
                        {step}
                      </div>
                    ))}
                  </div>
               </div>
             )}
          </div>

          {/* Citations - Only for Assistant */}
          {!isUser && message.citations && message.citations.length > 0 && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="flex flex-wrap gap-3 ml-1 mt-2"
            >
              {message.citations.map((cit) => (
                <button 
                  key={cit.id}
                  className="flex items-center space-x-2 bg-white border border-gray-200 hover:border-wpi-red hover:shadow-md transition-all text-base text-gray-600 px-4 py-2 rounded-lg"
                >
                  <Book size={18} className="text-wpi-red" />
                  <span className="font-medium truncate max-w-[200px]">{cit.source}</span>
                </button>
              ))}
            </motion.div>
          )}
          
          <span className={`text-sm text-gray-400 ${isUser ? 'text-right' : 'text-left'} px-1`}>
             {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </motion.div>
  );
};
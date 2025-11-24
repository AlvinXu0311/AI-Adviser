import { FC } from 'react';
import { Message, Role } from '../types';
import ReactMarkdown from 'react-markdown';
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
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-sm mt-1 ${
          isUser ? 'bg-gray-200' : 'bg-wpi-red'
        }`}>
          {isUser ? <User size={16} className="text-gray-600" /> : <Bot size={16} className="text-white" />}
        </div>

        {/* Bubble Content */}
        <div className="flex flex-col space-y-1">
          {/* Sender Name */}
          <span className={`text-[10px] font-semibold text-gray-400 ${isUser ? 'text-right' : 'text-left'} px-1`}>
            {isUser ? 'You' : 'Digital Adviser'}
          </span>

          <div className={`
            relative p-4 rounded-2xl shadow-sm text-sm leading-relaxed
            ${isUser 
              ? 'bg-wpi-red text-white rounded-tr-none' 
              : 'bg-white text-gray-800 border border-gray-100 rounded-tl-none'
            }
          `}>
             {/* Render Markdown Content */}
             <div className={`markdown-body ${isUser ? 'text-white' : 'text-gray-800'}`}>
                {/* Use a simplified renderer or standard styling */}
                <ReactMarkdown 
                  components={{
                    p: ({node, ...props}) => <p className="mb-2 last:mb-0" {...props} />,
                    ul: ({node, ...props}) => <ul className="list-disc ml-4 mb-2" {...props} />,
                    ol: ({node, ...props}) => <ol className="list-decimal ml-4 mb-2" {...props} />,
                    a: ({node, ...props}) => <a className="underline font-semibold hover:opacity-80" {...props} />,
                    strong: ({node, ...props}) => <strong className="font-bold" {...props} />
                  }}
                >
                  {message.content}
                </ReactMarkdown>
             </div>

             {/* Thought Steps (Agentic View) - Only for Assistant */}
             {!isUser && message.thoughtSteps && message.thoughtSteps.length > 0 && (
               <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-[10px] text-gray-400 font-semibold mb-1 uppercase tracking-wider flex items-center">
                    <CheckCircle2 size={10} className="mr-1 text-green-500" /> 
                    Agent Process
                  </p>
                  <div className="space-y-1">
                    {message.thoughtSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center text-[10px] text-gray-500 font-mono bg-gray-50 px-2 py-1 rounded">
                        <ArrowRight size={8} className="mr-2 text-gray-300" />
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
              className="flex flex-wrap gap-2 ml-1 mt-1"
            >
              {message.citations.map((cit) => (
                <button 
                  key={cit.id}
                  className="flex items-center space-x-1 bg-white border border-gray-200 hover:border-wpi-red hover:shadow-md transition-all text-[10px] text-gray-600 px-2 py-1 rounded-md"
                >
                  <Book size={10} className="text-wpi-red" />
                  <span className="font-medium truncate max-w-[150px]">{cit.source}</span>
                </button>
              ))}
            </motion.div>
          )}
          
          <span className={`text-[10px] text-gray-300 ${isUser ? 'text-right' : 'text-left'} px-1`}>
             {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </motion.div>
  );
};
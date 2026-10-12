import { useRef, useEffect, FC, Dispatch, SetStateAction } from 'react';
import { Message, ChatState, AgentStatus, AgentStep, Role } from '../types';
import { MessageBubble } from './MessageBubble';
import { InputArea } from './InputArea';
import { SAMPLE_QUESTIONS } from '../constants';
import chatService from '../services/chatService';

interface ChatInterfaceProps {
  chatState: ChatState;
  setChatState: Dispatch<SetStateAction<ChatState>>;
}

export const ChatInterface: FC<ChatInterfaceProps> = ({ chatState, setChatState }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatState.messages, chatState.agentStatus]);

  const ensureSessionId = () => {
    if (!sessionIdRef.current) {
      sessionIdRef.current = crypto.randomUUID();
    }
    return sessionIdRef.current;
  };

  const setAgentStatus = (status: AgentStatus) => {
    setChatState(prev => ({ ...prev, agentStatus: status }));
  };

  const mapEventToStatus = (eventType: string): AgentStatus | null => {
    switch (eventType) {
      case 'agent_action':
      case 'tool_start':
        return AgentStatus.SEARCHING_DB;
      case 'tool_end':
        return AgentStatus.READING_DOCS;
      case 'token':
        return AgentStatus.GENERATING;
      default:
        return null;
    }
  };

  const upsertAssistantMessage = (messageId: string, content: string) => {
    setChatState(prev => ({
      ...prev,
      messages: prev.messages.map(msg =>
        msg.id === messageId ? { ...msg, content } : msg
      )
    }));
  };

  const updateAgentSteps = (messageId: string, update: (steps: AgentStep[]) => AgentStep[]) => {
    setChatState(prev => ({
      ...prev,
      messages: prev.messages.map(msg =>
        msg.id === messageId
          ? { ...msg, agentSteps: update(msg.agentSteps || []) }
          : msg
      )
    }));
  };

  const appendAgentStep = (messageId: string, step: AgentStep) => {
    updateAgentSteps(messageId, steps => [...steps, step]);
  };

  // Attach a tool's output to the most recent running call of that tool
  const completeToolStep = (messageId: string, output: string) => {
    updateAgentSteps(messageId, steps => {
      const idx = steps.map(s => s.kind === 'tool' && s.status === 'running').lastIndexOf(true);
      if (idx === -1) return steps;
      return steps.map((s, i) => (i === idx && s.kind === 'tool' ? { ...s, output, status: 'done' } : s));
    });
  };

  const handleSendMessage = async (text: string) => {
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: Role.USER,
      content: text,
      timestamp: new Date()
    };

    const assistantMsgId = `assistant-${Date.now()}`;
    const assistantPlaceholder: Message = {
      id: assistantMsgId,
      role: Role.ASSISTANT,
      content: '',
      timestamp: new Date(),
      agentSteps: []
    };

    setChatState(prev => ({
      ...prev,
      messages: [...prev.messages, newUserMsg, assistantPlaceholder],
      isLoading: true,
      agentStatus: AgentStatus.THINKING
    }));

    try {
      const sessionId = ensureSessionId();
      let accumulated = '';

      await chatService.streamChat(
        {
          message: text,
          session_id: sessionId
        },
        (event) => {
          if (event.type === 'token') {
            const token = event.data?.content || '';
            accumulated += token;
            upsertAssistantMessage(assistantMsgId, accumulated);
            setAgentStatus(AgentStatus.GENERATING);
          } else if (event.type === 'stage') {
            const text = event.data?.content;
            if (text) appendAgentStep(assistantMsgId, { kind: 'stage', text });
          } else if (event.type === 'agent_action') {
            const thought = event.data?.thought;
            if (thought) appendAgentStep(assistantMsgId, { kind: 'thought', text: thought });
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'tool_start') {
            appendAgentStep(assistantMsgId, {
              kind: 'tool',
              tool: event.data?.tool_name || 'tool',
              input: event.data?.input || '',
              status: 'running'
            });
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'tool_end') {
            completeToolStep(assistantMsgId, event.data?.output || '');
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'agent_finish') {
            const thought = event.data?.thought;
            if (thought) appendAgentStep(assistantMsgId, { kind: 'thought', text: thought });
          } else if (event.type === 'final') {
            // Handle final response from intent pipeline
            const finalContent = event.data?.content || accumulated;
            accumulated = finalContent;
            upsertAssistantMessage(assistantMsgId, finalContent);
          } else if (event.type === 'error') {
            const message = event.data?.content || 'Unexpected error from agent.';
            upsertAssistantMessage(assistantMsgId, `${message}`);
          } else if (event.type === 'end') {
            setChatState(prev => ({ ...prev, isLoading: false, agentStatus: AgentStatus.IDLE }));
          } else {
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          }
        }
      );

      setChatState(prev => ({ ...prev, isLoading: false, agentStatus: AgentStatus.IDLE }));
    } catch (error) {
      console.error("Chat error", error);
      upsertAssistantMessage(assistantMsgId, 'Unable to reach the advising service.');
      setChatState(prev => ({ ...prev, isLoading: false, agentStatus: AgentStatus.IDLE }));
    }
  };

  const handleFileUpload = async (file: File) => {
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: Role.USER,
      content: `**Uploaded Document:** ${file.name}`,
      timestamp: new Date()
    };

    setChatState(prev => ({
      ...prev,
      messages: [...prev.messages, newUserMsg],
      isLoading: true,
      agentStatus: AgentStatus.READING_DOCS
    }));

    try {
      // Ensure session ID is created before upload so transcript is linked to this session
      const sessionId = ensureSessionId();
      const result = await chatService.extractTranscript(file, sessionId);
      const summaryLines: string[] = [];
      if (result.success && result.data) {
        const data = result.data;
        summaryLines.push(`**Transcript processed for ${data.student_name || 'student'}**`);
        if (data.program_info?.program_name) {
          summaryLines.push(`Program: ${data.program_info.program_name}`);
        }
        if (data.gpa) {
          summaryLines.push(`GPA: ${data.gpa}`);
        }
        if (Array.isArray(data.completed_courses) && data.completed_courses.length) {
          summaryLines.push(`Completed courses: ${data.completed_courses.length}`);
        }
        if (Array.isArray(data.current_courses) && data.current_courses.length) {
          summaryLines.push(`Current courses: ${data.current_courses.length}`);
        }
      } else {
        summaryLines.push(`Transcript extraction failed: ${result.error || 'Unknown error'}`);
      }

      const transcriptMsg: Message = {
        id: `transcript-${Date.now()}`,
        role: Role.ASSISTANT,
        content: summaryLines.join('\n'),
        timestamp: new Date()
      };

      setChatState(prev => ({
        ...prev,
        messages: [...prev.messages, transcriptMsg],
        isLoading: false,
        agentStatus: AgentStatus.IDLE
      }));
    } catch (error) {
      console.error("Upload error", error);
      const errorMsg: Message = {
        id: `transcript-error-${Date.now()}`,
        role: Role.ASSISTANT,
        content: 'Failed to process transcript. Please try again.',
        timestamp: new Date()
      };
      setChatState(prev => ({
        ...prev,
        messages: [...prev.messages, errorMsg],
        isLoading: false,
        agentStatus: AgentStatus.IDLE
      }));
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#f9fafb]">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {chatState.messages.map((msg, idx) => {
          const isLast = idx === chatState.messages.length - 1;
          return (
            <MessageBubble key={msg.id} message={msg} isLast={isLast} isStreaming={isLast && chatState.isLoading} />
          );
        })}

        {/* Agent Status Indicator - only until the live Agent Process panel has something to show */}
        {chatState.isLoading && !chatState.messages[chatState.messages.length - 1]?.agentSteps?.length && (
          <div className="flex justify-start animate-pulse">
            <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none py-4 px-6 shadow-sm flex items-center space-x-4">
              <div className="w-8 h-8 border-3 border-wpi-red border-t-transparent rounded-full animate-spin"></div>
              <span className="text-lg font-semibold text-wpi-red uppercase tracking-wide">
                 {/* Map the enum status to readable text via constants or direct logic */}
                 {chatState.agentStatus.replace('_', ' ')}...
              </span>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestion Chips */}
      {chatState.messages.length === 1 && !chatState.isLoading && (
        <div className="px-3 sm:px-8 pb-3 sm:pb-4">
          <div className="flex flex-wrap gap-2 sm:gap-4 justify-center">
            {SAMPLE_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(q)}
                className="text-xs sm:text-sm bg-white border border-gray-200 hover:border-wpi-red hover:text-wpi-red text-gray-600 px-3 sm:px-4 py-1.5 sm:py-2 rounded-full transition-colors shadow-sm"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-3 sm:p-6 bg-white border-t border-gray-100 shadow-sm relative z-10">
        <div className="max-w-5xl mx-auto">
          <InputArea 
            onSendMessage={handleSendMessage} 
            onFileUpload={handleFileUpload} 
            disabled={chatState.isLoading}
          />
          <div className="text-center mt-2 sm:mt-3">
            <p className="text-xs sm:text-sm text-gray-400">
              AI-generated responses. Check official documents for binding policies.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
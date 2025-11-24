import { useRef, useEffect, FC, Dispatch, SetStateAction } from 'react';
import { Message, ChatState, AgentStatus, Role } from '../types';
import { MessageBubble } from './MessageBubble';
import { InputArea } from './InputArea';
import { SAMPLE_QUESTIONS, ADVISING_TOPICS } from '../constants';
import chatService from '../services/chatService';

interface ChatInterfaceProps {
  chatState: ChatState;
  setChatState: Dispatch<SetStateAction<ChatState>>;
  selectedTopic: string | null;
  onSelectTopic: (topicId: string) => void;
}

export const ChatInterface: FC<ChatInterfaceProps> = ({ chatState, setChatState, selectedTopic, onSelectTopic }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | null>(null);
  const currentTopic = selectedTopic ? ADVISING_TOPICS.find(topic => topic.id === selectedTopic) : null;

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

  const appendThoughtStep = (messageId: string, step: string) => {
    setChatState(prev => ({
      ...prev,
      messages: prev.messages.map(msg =>
        msg.id === messageId
          ? { ...msg, thoughtSteps: [...(msg.thoughtSteps || []), step] }
          : msg
      )
    }));
  };

  const handleTopicSelection = (topicId: string) => {
    const topic = ADVISING_TOPICS.find(item => item.id === topicId);
    if (!topic) return;

    onSelectTopic(topicId);
    setChatState(prev => ({
      ...prev,
      messages: [
        ...prev.messages,
        {
          id: `topic-${Date.now()}`,
          role: Role.ASSISTANT,
          content: `Got it—we'll start with the "${topic.label}" topic. Tell me your question or upload a transcript when you're ready.`,
          timestamp: new Date()
        }
      ]
    }));
  };

  const handleSendMessage = async (text: string) => {
    if (!currentTopic) {
      return;
    }
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
      thoughtSteps: []
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
        { message: text, session_id: sessionId },
        (event) => {
          if (event.type === 'token') {
            const token = event.data?.content || '';
            accumulated += token;
            upsertAssistantMessage(assistantMsgId, accumulated);
            setAgentStatus(AgentStatus.GENERATING);
          } else if (event.type === 'agent_action') {
            const actionLog = event.data?.action?.log;
            if (actionLog) {
              appendThoughtStep(assistantMsgId, actionLog);
            }
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'tool_start') {
            const tool = event.data?.tool_name || 'Tool';
            appendThoughtStep(assistantMsgId, `Tool started: ${tool}`);
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'tool_end') {
            const output = event.data?.output;
            if (output) {
              appendThoughtStep(assistantMsgId, `Tool result: ${output}`);
            }
            const status = mapEventToStatus(event.type);
            if (status) setAgentStatus(status);
          } else if (event.type === 'agent_finish') {
            const finalText =
              event.data?.finish?.return_values?.output ||
              event.data?.finish?.return_values?.response ||
              accumulated;
            accumulated = finalText;
            upsertAssistantMessage(assistantMsgId, finalText);
          } else if (event.type === 'error') {
            const message = event.data?.content || 'Unexpected error from agent.';
            upsertAssistantMessage(assistantMsgId, `⚠️ ${message}`);
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
      upsertAssistantMessage(assistantMsgId, '⚠️ Unable to reach the advising service.');
      setChatState(prev => ({ ...prev, isLoading: false, agentStatus: AgentStatus.IDLE }));
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!currentTopic) {
      return;
    }
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: Role.USER,
      content: `📄 **Uploaded Document:** ${file.name}`,
      timestamp: new Date()
    };

    setChatState(prev => ({
      ...prev,
      messages: [...prev.messages, newUserMsg],
      isLoading: true,
      agentStatus: AgentStatus.READING_DOCS
    }));

    try {
      const result = await chatService.extractTranscript(file);
      const summaryLines: string[] = [];
      if (result.success && result.data) {
        const data = result.data;
        summaryLines.push(`📊 **Transcript processed for ${data.student_name || 'student'}**`);
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
        summaryLines.push(`⚠️ Transcript extraction failed: ${result.error || 'Unknown error'}`);
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
        content: '⚠️ Failed to process transcript. Please try again.',
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
        {!currentTopic && (
          <div className="bg-white border border-gray-200 rounded-3xl p-6 shadow-sm">
            <p className="text-xs font-semibold text-wpi-red uppercase tracking-[0.3em] mb-3">Start Here</p>
            <h3 className="text-xl font-semibold text-gray-800 mb-2">Choose an advising topic</h3>
            <p className="text-sm text-gray-600 mb-5">
              The Adviser Portal loads the right knowledge base, RAG tools, and guardrails based on your selection. Pick whichever topic matches your question best.
            </p>
            <div className="grid sm:grid-cols-3 gap-3">
              {ADVISING_TOPICS.map(topic => (
                <button
                  key={topic.id}
                  onClick={() => handleTopicSelection(topic.id)}
                  className="text-left border border-gray-200 rounded-2xl p-4 hover:border-wpi-red hover:bg-wpi-red/5 transition-all"
                >
                  <p className="text-sm font-semibold text-gray-800">{topic.label}</p>
                  <p className="text-xs text-gray-500 mt-1 leading-relaxed">{topic.description}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {currentTopic && (
          <div className="flex justify-center">
            <span className="text-xs font-semibold tracking-wide text-wpi-red bg-wpi-red/10 px-3 py-1 rounded-full">
              Active topic: {currentTopic.label}
            </span>
          </div>
        )}

        {chatState.messages.map((msg, idx) => (
          <MessageBubble key={msg.id} message={msg} isLast={idx === chatState.messages.length - 1} />
        ))}
        
        {/* Agent Status Indicator (Visualizing the "Agentic" part) */}
        {chatState.isLoading && (
          <div className="flex justify-start animate-pulse">
            <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none py-3 px-4 shadow-sm flex items-center space-x-3">
              <div className="w-5 h-5 border-2 border-wpi-red border-t-transparent rounded-full animate-spin"></div>
              <span className="text-xs font-semibold text-wpi-red uppercase tracking-wide">
                 {/* Map the enum status to readable text via constants or direct logic */}
                 {chatState.agentStatus.replace('_', ' ')}...
              </span>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestion Chips */}
      {currentTopic && chatState.messages.length === 1 && !chatState.isLoading && (
        <div className="px-6 pb-2">
          <div className="flex flex-wrap gap-2 justify-center">
            {SAMPLE_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(q)}
                className="text-xs bg-white border border-gray-200 hover:border-wpi-red hover:text-wpi-red text-gray-600 px-3 py-1.5 rounded-full transition-colors shadow-sm"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-100 shadow-sm relative z-10">
        <div className="max-w-4xl mx-auto">
          <InputArea 
            onSendMessage={handleSendMessage} 
            onFileUpload={handleFileUpload} 
            disabled={chatState.isLoading || !currentTopic} 
            placeholder={currentTopic ? undefined : 'Select a topic above before you start typing'}
          />
          <div className="text-center mt-2">
            <p className="text-[10px] text-gray-400">
              AI-generated responses powered by WPI RAG & Agentic LLM. Check official documents for binding policies.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
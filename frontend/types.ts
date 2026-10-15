export enum Role {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system'
}

export enum AgentStatus {
  IDLE = 'idle',
  THINKING = 'thinking',
  SEARCHING_DB = 'searching_db',
  READING_DOCS = 'reading_docs',
  GENERATING = 'generating'
}

// User authentication type
export interface User {
  email: string;
  name: string;
  loginTime: Date;
}

// One entry in the agent's visible reasoning trace
export type AgentStep =
  | { kind: 'stage'; text: string }
  | { kind: 'thought'; text: string }
  | { kind: 'tool'; id?: string; tool: string; input: string; output?: string; status: 'running' | 'done' };

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  // For showing agent thought process
  agentSteps?: AgentStep[];
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  agentStatus: AgentStatus;
}
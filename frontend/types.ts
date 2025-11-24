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

export interface Citation {
  id: string;
  title: string;
  source: string; // e.g., "Student Handbook 2024"
  url?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  citations?: Citation[];
  // For showing agent thought process
  thoughtSteps?: string[]; 
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  agentStatus: AgentStatus;
}
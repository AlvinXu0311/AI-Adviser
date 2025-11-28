import { AgentStatus } from './types';

export const APP_NAME = "WPI Business School Digital Adviser";

export const AGENT_STATUS_MESSAGES: Record<AgentStatus, string> = {
  [AgentStatus.IDLE]: "Ready",
  [AgentStatus.THINKING]: "Analyzing request...",
  [AgentStatus.SEARCHING_DB]: "Querying Database...",
  [AgentStatus.READING_DOCS]: "Processing information...",
  [AgentStatus.GENERATING]: "Drafting response..."
};

export const SAMPLE_QUESTIONS = [
  "What are the prerequisites for the MBA program?",
  "Who teaches the Data Mining for Business course?",
  "Tell me about MSIT specializations",
  "Check my degree progress (Upload Transcript)"
];

// Mock database sources for visual effect
export const MOCK_SOURCES = [
  { id: 'src-1', title: 'Graduate Catalog 2024-25', source: 'PDF' },
  { id: 'src-2', title: 'Business School Faculty Directory', source: 'DB' },
  { id: 'src-3', title: 'WPI International Student Handbook', source: 'Web' },
];
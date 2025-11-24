import { AgentStatus } from './types';

export const APP_NAME = "WPI Business School Digital Adviser";

export const AGENT_STATUS_MESSAGES: Record<AgentStatus, string> = {
  [AgentStatus.IDLE]: "Ready",
  [AgentStatus.THINKING]: "Analyzing request...",
  [AgentStatus.SEARCHING_DB]: "Querying Local Vector RAG...",
  [AgentStatus.READING_DOCS]: "Synthesizing from Knowledge Base...",
  [AgentStatus.GENERATING]: "Drafting response..."
};

export const SAMPLE_QUESTIONS = [
  "What are the prerequisites for the MBA program?",
  "Who teaches the Data Mining for Business course?",
  "Can you explain the OPT policy for international students?",
  "Check my degree progress (Upload Transcript)"
];

export const ADVISING_TOPICS = [
  {
    id: 'general',
    label: 'General Advising',
    description: 'Program overview, policies, common questions',
  },
  {
    id: 'course',
    label: 'Courses & Planning',
    description: 'Schedules, catalog details, prerequisites',
  },
  {
    id: 'entr',
    label: 'ENTR & Venture Track',
    description: 'Entrepreneurship resources, pitch labs, programs',
  },
];

// Mock database sources for visual effect
export const MOCK_SOURCES = [
  { id: 'src-1', title: 'Graduate Catalog 2024-25', source: 'PDF' },
  { id: 'src-2', title: 'Business School Faculty Directory', source: 'DB' },
  { id: 'src-3', title: 'WPI International Student Handbook', source: 'Web' },
];
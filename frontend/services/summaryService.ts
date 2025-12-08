/**
 * Summary Service
 * Calls backend API to generate AI-powered chat summaries using Gemini
 */

import { Message } from '../types';

const API_BASE_URL = import.meta.env.VITE_BACKEND_URL || '';

export interface StudentInfo {
  program: string;
  coursesCompleted: string[];
  coursesInProgress: string[];
  gpa: string;
  specialties: string[];
}

export interface ChatSummary {
  success: boolean;
  summary: string;
  studentInfo?: StudentInfo;
  keyTopics: string[];
  requirementsDiscussed: string[];
  recommendations: string[];
  error?: string;
}

interface MessageItem {
  role: string;
  content: string;
  timestamp: string;
}

/**
 * Generate a detailed summary of the chat conversation using Gemini API
 */
export async function generateChatSummary(
  messages: Message[],
  userName: string = 'User'
): Promise<ChatSummary> {
  try {
    // Filter out system messages and prepare for API
    const messageItems: MessageItem[] = messages
      .filter(m => m.role !== 'system')
      .map(m => ({
        role: m.role,
        content: m.content,
        timestamp: m.timestamp ? new Date(m.timestamp).toISOString() : '',
      }));

    if (messageItems.length === 0) {
      return {
        success: false,
        summary: '',
        keyTopics: [],
        requirementsDiscussed: [],
        recommendations: [],
        error: 'No messages to summarize',
      };
    }

    const response = await fetch(`${API_BASE_URL}/api/summarize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        messages: messageItems,
        user_name: userName,
        include_recommendations: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();

    // Parse student_info from snake_case to camelCase
    let studentInfo: StudentInfo | undefined;
    if (data.student_info) {
      studentInfo = {
        program: data.student_info.program || '',
        coursesCompleted: data.student_info.courses_completed || [],
        coursesInProgress: data.student_info.courses_in_progress || [],
        gpa: data.student_info.gpa || '',
        specialties: data.student_info.specialties || [],
      };
    }

    return {
      success: data.success,
      summary: data.summary || '',
      studentInfo,
      keyTopics: data.key_topics || [],
      requirementsDiscussed: data.requirements_discussed || [],
      recommendations: data.recommendations || [],
      error: data.error || '',
    };
  } catch (error) {
    console.error('[Summary] Failed to generate summary:', error);
    return {
      success: false,
      summary: '',
      keyTopics: [],
      requirementsDiscussed: [],
      recommendations: [],
      error: error instanceof Error ? error.message : 'Failed to generate summary',
    };
  }
}

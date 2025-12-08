/**
 * PDF Export Service
 * Generates PDF summary of chat conversations with AI-generated insights
 */

import { jsPDF } from 'jspdf';
import { Message } from '../types';
import { ChatSummary } from './summaryService';

interface ChatSummaryOptions {
  userName: string;
  sessionDate: Date;
  messages: Message[];
  aiSummary?: ChatSummary;
  includeTimestamps?: boolean;
  includeFullConversation?: boolean;
}

/**
 * Strip markdown formatting for plain text PDF
 */
function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // Bold
    .replace(/\*([^*]+)\*/g, '$1')       // Italic
    .replace(/`([^`]+)`/g, '$1')         // Inline code
    .replace(/```[\s\S]*?```/g, '')      // Code blocks
    .replace(/^#+\s+/gm, '')             // Headers
    .replace(/^[-*]\s+/gm, '• ')         // List items
    .replace(/^\d+\.\s+/gm, '')          // Numbered lists
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Links
    .replace(/\n{3,}/g, '\n\n')          // Multiple newlines
    .trim();
}

/**
 * Format date for display
 */
function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/**
 * Format time only
 */
function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/**
 * Generate PDF summary of chat conversation
 */
export function generateChatPDF(options: ChatSummaryOptions): void {
  const { userName, sessionDate, messages, aiSummary, includeTimestamps = true, includeFullConversation = true } = options;
  
  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });
  
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 20;
  const contentWidth = pageWidth - margin * 2;
  let yPosition = margin;
  
  // Helper function to add new page if needed
  const checkNewPage = (requiredSpace: number = 20) => {
    if (yPosition + requiredSpace > pageHeight - margin - 15) {
      pdf.addPage();
      yPosition = margin;
      return true;
    }
    return false;
  };
  
  // Helper function to add wrapped text
  const addWrappedText = (text: string, fontSize: number, isBold: boolean = false, color: [number, number, number] = [0, 0, 0], indent: number = 0) => {
    pdf.setFontSize(fontSize);
    pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
    pdf.setTextColor(...color);
    
    const lines = pdf.splitTextToSize(text, contentWidth - indent);
    const lineHeight = fontSize * 0.5;
    
    for (const line of lines) {
      checkNewPage(lineHeight);
      pdf.text(line, margin + indent, yPosition);
      yPosition += lineHeight;
    }
  };

  // Helper to add section header
  const addSectionHeader = (title: string) => {
    checkNewPage(20);
    yPosition += 5;
    pdf.setFontSize(12);
    pdf.setFont('helvetica', 'bold');
    pdf.setTextColor(172, 43, 55);
    pdf.text(title, margin, yPosition);
    yPosition += 3;
    pdf.setDrawColor(172, 43, 55);
    pdf.setLineWidth(0.5);
    pdf.line(margin, yPosition, margin + 50, yPosition);
    yPosition += 8;
  };
  
  // ===== HEADER =====
  // WPI Logo placeholder (red rectangle)
  pdf.setFillColor(172, 43, 55); // WPI Red
  pdf.rect(margin, yPosition - 5, 10, 10, 'F');
  
  // Title
  pdf.setFontSize(18);
  pdf.setFont('helvetica', 'bold');
  pdf.setTextColor(172, 43, 55);
  pdf.text('WPI Business School', margin + 15, yPosition);
  yPosition += 7;
  
  pdf.setFontSize(14);
  pdf.setTextColor(100, 100, 100);
  pdf.text('Digital Adviser - Session Summary', margin + 15, yPosition);
  yPosition += 15;
  
  // Divider line
  pdf.setDrawColor(200, 200, 200);
  pdf.setLineWidth(0.5);
  pdf.line(margin, yPosition, pageWidth - margin, yPosition);
  yPosition += 10;
  
  // ===== SESSION INFO =====
  pdf.setFontSize(10);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(80, 80, 80);
  
  pdf.text(`Student: ${userName}`, margin, yPosition);
  yPosition += 5;
  pdf.text(`Date: ${formatDate(sessionDate)}`, margin, yPosition);
  yPosition += 5;
  
  const userMsgCount = messages.filter(m => m.role === 'user').length;
  const adviserMsgCount = messages.filter(m => m.role === 'assistant').length;
  pdf.text(`Conversation: ${userMsgCount} questions, ${adviserMsgCount} responses`, margin, yPosition);
  yPosition += 10;
  
  // ===== AI SUMMARY (if available) =====
  if (aiSummary && aiSummary.success && aiSummary.summary) {
    addSectionHeader('Session Summary');
    addWrappedText(aiSummary.summary, 10, false, [40, 40, 40]);
    yPosition += 5;
    
    // Student Info (if available)
    if (aiSummary.studentInfo) {
      const info = aiSummary.studentInfo;
      const hasStudentInfo = info.program || info.coursesCompleted.length > 0 || 
                            info.coursesInProgress.length > 0 || info.gpa || 
                            info.specialties.length > 0;
      
      if (hasStudentInfo) {
        addSectionHeader('Student Information');
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        pdf.setTextColor(60, 60, 60);
        
        if (info.program) {
          checkNewPage(8);
          pdf.text(`Program: ${info.program}`, margin + 3, yPosition);
          yPosition += 5;
        }
        if (info.gpa) {
          checkNewPage(8);
          pdf.text(`GPA: ${info.gpa}`, margin + 3, yPosition);
          yPosition += 5;
        }
        if (info.specialties.length > 0) {
          checkNewPage(8);
          pdf.text(`Specialties: ${info.specialties.join(', ')}`, margin + 3, yPosition);
          yPosition += 5;
        }
        if (info.coursesCompleted.length > 0) {
          checkNewPage(8);
          pdf.setFont('helvetica', 'bold');
          pdf.text('Courses Completed:', margin + 3, yPosition);
          yPosition += 5;
          pdf.setFont('helvetica', 'normal');
          for (const course of info.coursesCompleted.slice(0, 10)) {
            checkNewPage(5);
            pdf.text(`  •  ${course}`, margin + 5, yPosition);
            yPosition += 5;
          }
        }
        if (info.coursesInProgress.length > 0) {
          checkNewPage(8);
          pdf.setFont('helvetica', 'bold');
          pdf.text('Courses In Progress:', margin + 3, yPosition);
          yPosition += 5;
          pdf.setFont('helvetica', 'normal');
          for (const course of info.coursesInProgress.slice(0, 10)) {
            checkNewPage(5);
            pdf.text(`  •  ${course}`, margin + 5, yPosition);
            yPosition += 5;
          }
        }
        yPosition += 5;
      }
    }
    
    // Key Topics
    if (aiSummary.keyTopics && aiSummary.keyTopics.length > 0) {
      addSectionHeader('Key Topics Discussed');
      for (const topic of aiSummary.keyTopics) {
        checkNewPage(8);
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        pdf.setTextColor(60, 60, 60);
        pdf.text(`•  ${topic}`, margin + 3, yPosition);
        yPosition += 5;
      }
      yPosition += 5;
    }
    
    // Requirements Discussed (new section)
    if (aiSummary.requirementsDiscussed && aiSummary.requirementsDiscussed.length > 0) {
      addSectionHeader('Requirements Discussed');
      for (const req of aiSummary.requirementsDiscussed) {
        checkNewPage(8);
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'normal');
        pdf.setTextColor(60, 60, 60);
        pdf.text(`•  ${req}`, margin + 3, yPosition);
        yPosition += 5;
      }
      yPosition += 5;
    }
    
    // Recommendations
    if (aiSummary.recommendations && aiSummary.recommendations.length > 0) {
      addSectionHeader('Recommendations & Next Steps');
      for (let i = 0; i < aiSummary.recommendations.length; i++) {
        checkNewPage(10);
        pdf.setFontSize(10);
        pdf.setFont('helvetica', 'bold');
        pdf.setTextColor(172, 43, 55);
        pdf.text(`${i + 1}.`, margin + 3, yPosition);
        pdf.setFont('helvetica', 'normal');
        pdf.setTextColor(40, 40, 40);
        
        const recLines = pdf.splitTextToSize(aiSummary.recommendations[i], contentWidth - 12);
        for (const line of recLines) {
          pdf.text(line, margin + 10, yPosition);
          yPosition += 5;
        }
        yPosition += 2;
      }
    }
  }
  
  // ===== FULL CONVERSATION (optional) =====
  if (includeFullConversation) {
    addSectionHeader('Full Conversation');
    
    for (const message of messages) {
      checkNewPage(25);
      
      const isUser = message.role === 'user';
      const senderLabel = isUser ? 'You' : 'Adviser';
      const labelColor: [number, number, number] = isUser ? [0, 100, 180] : [172, 43, 55];
      
      // Sender label with timestamp
      pdf.setFontSize(10);
      pdf.setFont('helvetica', 'bold');
      pdf.setTextColor(...labelColor);
      
      let label = senderLabel;
      if (includeTimestamps && message.timestamp) {
        label += ` (${formatTime(new Date(message.timestamp))})`;
      }
      pdf.text(label, margin, yPosition);
      yPosition += 5;
      
      // Message content
      const cleanContent = stripMarkdown(message.content);
      addWrappedText(cleanContent, 9, false, [50, 50, 50], 3);
      yPosition += 6;
    }
  }
  
  // ===== FOOTER on all pages =====
  const pageCount = pdf.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    pdf.setPage(i);
    const footerY = pageHeight - 10;
    pdf.setFontSize(8);
    pdf.setFont('helvetica', 'normal');
    pdf.setTextColor(150, 150, 150);
    pdf.text(
      `Generated on ${formatDate(new Date())} | WPI Business School Digital Adviser`,
      margin,
      footerY
    );
    pdf.text(
      `Page ${i} of ${pageCount}`,
      pageWidth - margin - 20,
      footerY
    );
  }
  
  // Generate filename
  const dateStr = new Date().toISOString().split('T')[0];
  const filename = `WPI_Adviser_Chat_${dateStr}.pdf`;
  
  // Download
  pdf.save(filename);
}

/**
 * Generate a text-based summary for quick export
 */
export function generateChatText(messages: Message[]): string {
  const lines: string[] = [
    'WPI Business School Digital Adviser',
    'Chat Summary',
    `Generated: ${formatDate(new Date())}`,
    '',
    '='.repeat(50),
    '',
  ];
  
  for (const message of messages) {
    const sender = message.role === 'user' ? 'You' : 'Adviser';
    const time = message.timestamp ? formatTime(new Date(message.timestamp)) : '';
    
    lines.push(`[${sender}] ${time}`);
    lines.push(stripMarkdown(message.content));
    lines.push('');
  }
  
  return lines.join('\n');
}

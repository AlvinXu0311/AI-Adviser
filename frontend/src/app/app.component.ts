import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ChatService, ChatResponse, StreamEvent } from './services/chat.service';
import { MatToolbarModule } from '@angular/material/toolbar';
import { ExtractedTranscriptData } from './services/pdf-upload.service';
import { FormatAnswerPipe } from './format-answer.pipe';

interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
  thinking?: boolean;
}

const HISTORY_COLLAPSE_THRESHOLD = 15; // Collapse history after 15 messages

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  messages: Message[] = [];
  messageText = '';
  loading = false;
  showPdfUpload = true;
  transcriptData: ExtractedTranscriptData | null = null;
  showHistory = false; // Collapsed by default when threshold is exceeded
  historyCollapsed = false; // Tracks if history is manually collapsed
  sessionId: string = ''; // Session ID for conversation history

  constructor(private chatService: ChatService) {
    // Generate a unique session ID for this conversation
    this.sessionId = this.generateSessionId();
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  /**
   * Handle transcript upload from PDF component
   */
  onTranscriptLoaded(data: ExtractedTranscriptData): void {
    this.transcriptData = data;
    this.showPdfUpload = true;

    // Add system message about transcript
    const systemMessage: Message = {
      text: `I've successfully loaded your academic transcript. I now have access to your course history, GPA, and program information. How can I help you today?`,
      isUser: false,
      timestamp: new Date()
    };
    this.messages.push(systemMessage);
  }

  sendMessage(): void {
    if (!this.messageText?.trim() || this.loading) return;

    const userMessage: Message = {
      text: this.messageText,
      isUser: true,
      timestamp: new Date()
    };

    this.messages.push(userMessage);
    this.loading = true;
    const temp = this.messageText;
    this.messageText = '';

    // Build conversation history for context (exclude the current message being sent)
    const conversationHistory = this.messages
      .slice(0, -1) // Exclude the message we just added
      .map(msg => ({
        role: msg.isUser ? 'user' as const : 'assistant' as const,
        content: msg.text,
        timestamp: msg.timestamp
      }));

    // Include transcript data context in request if available
    const payload = {
      message: temp,
      transcriptContext: this.transcriptData ? {
        studentName: this.transcriptData.studentName,
        gpa: this.transcriptData.gpa,
        program: this.transcriptData.programInfo?.programName,
        courseCount: (this.transcriptData.completedCourses?.length || 0) + (this.transcriptData.currentCourses?.length || 0)
      } : null,
      conversationHistory: conversationHistory,
      sessionId: this.sessionId
    };

    console.log('📤 Sending message with conversation history:', {
      messageCount: this.messages.length,
      historyLength: conversationHistory.length,
      sessionId: this.sessionId
    });

    let botMessage: Message = {
      text: '',
      isUser: false,
      timestamp: new Date(),
      thinking: true
    };
    this.messages.push(botMessage);

    this.chatService.sendMessage(payload).subscribe({
      next: (event: StreamEvent) => {
        botMessage.thinking = false;
        if (event.type === 'token') {
          botMessage.text += event.content;
        } else if (event.type === 'agent_action') {
          botMessage.text += `\n\n[USING TOOL: ${event.action.tool}]\n`;
          if (event.action.tool_input) {
            botMessage.text += `Input: ${event.action.tool_input}\n`;
          }
        } else if (event.type === 'tool_end') {
          botMessage.text += `\n[TOOL RESULT]\n${event.output}\n`;
        } else if (event.type === 'agent_finish') {
          // Append final answer to the thinking process with strong visual separation
          botMessage.text += `\n\n${'='.repeat(50)}\nFINAL ANSWER\n${'='.repeat(50)}\n\n${event.finish.return_values.output}`;
        }
      },
      error: (err) => {
        console.error('Chat error:', err);
        botMessage.text = 'Sorry, an error occurred while fetching the response.';
        botMessage.thinking = false;
        this.loading = false;
      },
      complete: () => {
        console.log('Chat request completed');
        botMessage.thinking = false;
        this.loading = false;
      }
    });
  }

  /**
   * Toggle PDF upload visibility
   */
  togglePdfUpload(): void {
    this.showPdfUpload = !this.showPdfUpload;
  }

  /**
   * Toggle message history visibility
   */
  toggleHistory(): void {
    this.showHistory = !this.showHistory;
  }

  /**
   * Get messages to display - either all or just recent ones
   */
  get displayMessages(): Message[] {
    if (this.showHistory || this.messages.length <= HISTORY_COLLAPSE_THRESHOLD) {
      return this.messages;
    }
    // Show only recent messages when history is collapsed
    return this.messages.slice(-HISTORY_COLLAPSE_THRESHOLD);
  }

  /**
   * Check if history should be collapsed
   */
  get shouldShowHistoryToggle(): boolean {
    return this.messages.length > HISTORY_COLLAPSE_THRESHOLD;
  }

  /**
   * Get the number of hidden messages
   */
  get hiddenMessageCount(): number {
    return Math.max(0, this.messages.length - HISTORY_COLLAPSE_THRESHOLD);
  }

  /**
   * Generate a unique session ID for conversation tracking
   */
  private generateSessionId(): string {
    const timestamp = Date.now();
    const randomStr = Math.random().toString(36).substring(2, 15);
    return `session_${timestamp}_${randomStr}`;
  }

  private scrollToBottom(): void {
    try {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch (e) {
      // ignore
    }
  }
}

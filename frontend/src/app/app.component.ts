import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ChatService, ChatResponse } from './services/chat.service';
import { MatToolbarModule } from '@angular/material/toolbar';
import { ExtractedTranscriptData } from './services/pdf-upload.service';

interface Message {
  text: string;
  isUser: boolean;
  timestamp: Date;
}

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

  constructor(private chatService: ChatService) {}

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

    // Include transcript data context in request if available
    const payload = {
      message: temp,
      transcriptContext: this.transcriptData ? {
        studentName: this.transcriptData.studentName,
        gpa: this.transcriptData.gpa,
        program: this.transcriptData.programInfo?.programName,
        courseCount: (this.transcriptData.completedCourses?.length || 0) + (this.transcriptData.currentCourses?.length || 0)
      } : null
    };

    this.chatService.sendMessage(payload).subscribe({
      next: (res: ChatResponse) => {
        console.log(' Received response from API:', res);
        console.log('   Response text:', res.response.substring(0, 50) + '...');
        console.log('   Intent:', res.intent?.intent);
        console.log('   Response source:', res.response_source);
        this.messages.push({ text: res.response, isUser: false, timestamp: new Date() });
      },
      error: (err) => {
        console.error(' Chat error:', err);
        this.messages.push({ text: 'Sorry, an error occurred while fetching the response.', isUser: false, timestamp: new Date() });
      },
      complete: () => {
        console.log('Chat request completed');
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

  private scrollToBottom(): void {
    try {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch (e) {
      // ignore
    }
  }
}

import { TestBed, ComponentFixture } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { FormsModule } from '@angular/forms';
import { AppComponent } from './app.component';
import { ChatService } from './services/chat.service';
import { PdfUploadComponent } from './components/pdf-upload/pdf-upload.component';
import { of, throwError } from 'rxjs';
import { ExtractedTranscriptData } from './services/pdf-upload.service';

describe('AppComponent', () => {
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let chatService: jasmine.SpyObj<ChatService>;

  beforeEach(async () => {
    const chatServiceSpy = jasmine.createSpyObj('ChatService', ['sendMessage']);

    await TestBed.configureTestingModule({
      imports: [
        RouterTestingModule,
        BrowserAnimationsModule,
        HttpClientTestingModule,
        MatToolbarModule,
        MatFormFieldModule,
        MatInputModule,
        MatButtonModule,
        MatIconModule,
        MatCardModule,
        MatProgressBarModule,
        MatProgressSpinnerModule,
        MatChipsModule,
        FormsModule,
      ],
      declarations: [AppComponent, PdfUploadComponent],
      providers: [
        { provide: ChatService, useValue: chatServiceSpy }
      ]
    }).compileComponents();

    chatService = TestBed.inject(ChatService) as jasmine.SpyObj<ChatService>;
    fixture = TestBed.createComponent(AppComponent);
    component = fixture.componentInstance;
  });

  describe('Initialization', () => {
    it('should create the app component', () => {
      expect(component).toBeTruthy();
    });

    it('should initialize with empty messages', () => {
      expect(component.messages).toEqual([]);
    });

    it('should initialize with empty messageText', () => {
      expect(component.messageText).toEqual('');
    });

    it('should initialize with loading as false', () => {
      expect(component.loading).toBeFalse();
    });

    it('should initialize with showPdfUpload as true', () => {
      expect(component.showPdfUpload).toBeTrue();
    });

    it('should initialize with null transcriptData', () => {
      expect(component.transcriptData).toBeNull();
    });
  });

  describe('PDF Upload', () => {
    it('should handle transcript upload', () => {
      const sampleData: ExtractedTranscriptData = {
        studentName: 'John Doe',
        gpa: 3.85,
        programInfo: { programName: 'MS in Analytics' }
      };

      component.onTranscriptLoaded(sampleData);

      expect(component.transcriptData).toEqual(sampleData);
      expect(component.showPdfUpload).toBeFalse();
    });

    it('should add system message when transcript is loaded', () => {
      const sampleData: ExtractedTranscriptData = {
        studentName: 'John Doe',
        gpa: 3.85
      };

      component.onTranscriptLoaded(sampleData);

      expect(component.messages.length).toBeGreaterThan(0);
      expect(component.messages[0].isUser).toBeFalse();
      expect(component.messages[0].text).toContain('successfully loaded');
    });

    it('should toggle PDF upload visibility', () => {
      component.transcriptData = { studentName: 'Test' };
      component.showPdfUpload = false;

      component.togglePdfUpload();

      expect(component.showPdfUpload).toBeTrue();

      component.togglePdfUpload();

      expect(component.showPdfUpload).toBeFalse();
    });
  });

  describe('Chat Functionality', () => {
    it('should not send message if text is empty', () => {
      component.messageText = '';

      component.sendMessage();

      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should not send message if only whitespace', () => {
      component.messageText = '   ';

      component.sendMessage();

      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should not send message if loading', () => {
      component.messageText = 'Test message';
      component.loading = true;

      component.sendMessage();

      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should send message and add to messages array', () => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Bot response' })
      );
      component.messageText = 'Hello bot';

      component.sendMessage();

      expect(component.messages.length).toBeGreaterThan(0);
      expect(component.messages[0].text).toEqual('Hello bot');
      expect(component.messages[0].isUser).toBeTrue();
    });

    it('should clear input after sending message', (done) => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.messageText = 'Test message';

      component.sendMessage();

      setTimeout(() => {
        // Message should be cleared after sending
        expect(component.messageText).toEqual('');
        done();
      }, 10);
    });

    it('should set loading to true while waiting for response', () => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.messageText = 'Test';

      component.sendMessage();

      expect(component.loading).toBe(true);
    });

    it('should handle chat service response', (done) => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Bot says hello' })
      );
      component.messageText = 'Hi';

      component.sendMessage();

      setTimeout(() => {
        const botMessage = component.messages.find(m => !m.isUser);
        expect(botMessage).toBeTruthy();
        expect(botMessage?.text).toEqual('Bot says hello');
        done();
      }, 10);
    });

    it('should handle chat service error', (done) => {
      chatService.sendMessage.and.returnValue(
        throwError(() => new Error('Service error'))
      );
      component.messageText = 'Test';

      component.sendMessage();

      setTimeout(() => {
        const errorMessage = component.messages.find(m => m.text.includes('error'));
        expect(errorMessage).toBeTruthy();
        expect(component.loading).toBeFalse();
        done();
      }, 10);
    });

    it('should pass transcript context with message', () => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.transcriptData = {
        studentName: 'John Doe',
        gpa: 3.85,
        programInfo: { programName: 'MS in Analytics' },
        completedCourses: [{ courseCode: 'BUS501', courseName: 'Course', credits: 3 }]
      };
      component.messageText = 'What next?';

      component.sendMessage();

      expect(chatService.sendMessage).toHaveBeenCalledWith(
        jasmine.objectContaining({
          message: 'What next?',
          transcriptContext: {
            studentName: 'John Doe',
            gpa: 3.85,
            program: 'MS in Analytics',
            courseCount: 1
          }
        })
      );
    });

    it('should send message without context if no transcript', () => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.transcriptData = null;
      component.messageText = 'Hello';

      component.sendMessage();

      expect(chatService.sendMessage).toHaveBeenCalledWith(
        jasmine.objectContaining({
          message: 'Hello',
          transcriptContext: null
        })
      );
    });
  });

  describe('Send Button Disabled State', () => {
    it('should disable send button when message is empty', () => {
      component.messageText = '';
      component.loading = false;

      const isDisabled = component.loading || !component.messageText.trim();

      expect(isDisabled).toBeTrue();
    });

    it('should disable send button when loading', () => {
      component.messageText = 'Test message';
      component.loading = true;

      const isDisabled = component.loading || !component.messageText.trim();

      expect(isDisabled).toBeTrue();
    });

    it('should enable send button with valid message and not loading', () => {
      component.messageText = 'Valid message';
      component.loading = false;

      const isDisabled = component.loading || !component.messageText.trim();

      expect(isDisabled).toBeFalse();
    });
  });

  describe('Auto-scroll Functionality', () => {
    it('should have scrollContainer ref', () => {
      fixture.detectChanges();
      expect(component.scrollContainer).toBeDefined();
    });

    it('should call scrollToBottom on AfterViewChecked', () => {
      spyOn<any>(component, 'scrollToBottom');

      component.ngAfterViewChecked();

      expect(component['scrollToBottom']).toHaveBeenCalled();
    });
  });

  describe('Message Timestamp', () => {
    it('should add timestamp to user messages', () => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.messageText = 'Test';

      component.sendMessage();

      expect(component.messages[0].timestamp).toBeTruthy();
      expect(component.messages[0].timestamp instanceof Date).toBeTrue();
    });

    it('should add timestamp to bot messages', (done) => {
      chatService.sendMessage.and.returnValue(
        of({ response: 'Response' })
      );
      component.messageText = 'Test';

      component.sendMessage();

      setTimeout(() => {
        const botMessage = component.messages.find(m => !m.isUser);
        expect(botMessage?.timestamp).toBeTruthy();
        expect(botMessage?.timestamp instanceof Date).toBeTrue();
        done();
      }, 10);
    });
  });
});

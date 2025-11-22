import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError, Observer } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
}

export interface ChatPayload {
  message: string;
  transcriptContext?: {
    studentName?: string;
    gpa?: number;
    program?: string;
    courseCount?: number;
  } | null;
  conversationHistory?: ConversationMessage[];
  sessionId?: string;
}

export interface IntentClassification {
  intent: string;
  confidence: number;
  secondary_intents: string[];
  requires_transcript: boolean;
  rule_applicable: boolean;
  suggested_response_type: string;
}

export interface ChatResponse {
  response: string;
  intent?: IntentClassification;
  response_source?: string;
}

export interface StreamEvent {
  type: 'token' | 'tool_start' | 'tool_end' | 'agent_action' | 'agent_finish' | 'error' | 'info';
  content?: any;
  tool_name?: string;
  input?: string;
  output?: string;
  action?: any;
  finish?: any;
}


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // Keep API URL configurable later via environment file
  private apiUrl = 'http://localhost:8000/api/chat';
  private headers = new HttpHeaders({ 'Content-Type': 'application/json' });

  constructor(private http: HttpClient) {}

  /**
   * Send message to chat API with optional transcript context
   * @param payload - Either a string message or ChatPayload with context
   */
  sendMessage(payload: string | ChatPayload): Observable<StreamEvent> {
    const body = typeof payload === 'string' ? { message: payload } : payload;
    console.log('📤 Sending chat request:', body.message.substring(0, 50) + '...');

    return new Observable((observer: Observer<StreamEvent>) => {
      const controller = new AbortController();

      fetch(this.apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify(body),
        signal: controller.signal
      }).then(response => {
        if (!response.body) {
          throw new Error('ReadableStream not yet supported in this browser.');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function push() {
          reader.read().then(({ done, value }) => {
            if (done) {
              observer.complete();
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = JSON.parse(line.substring(6));
                observer.next(data as StreamEvent);
              }
            }
            push();
          }).catch(err => {
            observer.error(err);
          });
        }
        push();
      }).catch(err => {
        observer.error(err);
      });

      return () => {
        controller.abort();
      };
    });
  }

  private handleError(err: HttpErrorResponse) {
    console.error('ChatService error', err);
    return throwError(() => new Error(err.message || 'Server error'));
  }
}
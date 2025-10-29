import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ChatPayload {
  message: string;
  transcriptContext?: {
    studentName?: string;
    gpa?: number;
    program?: string;
    courseCount?: number;
  } | null;
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
  sendMessage(payload: string | ChatPayload): Observable<ChatResponse> {
    const body = typeof payload === 'string' ? { message: payload } : payload;
    console.log('📤 Sending chat request:', body.message.substring(0, 50) + '...');

    return this.http.post<ChatResponse>(this.apiUrl, body, { headers: this.headers })
      .pipe(
        catchError((error) => {
          console.error('❌ ChatService error:', error);
          return throwError(() => new Error(error.message || 'Server error'));
        })
      );
  }

  private handleError(err: HttpErrorResponse) {
    console.error('ChatService error', err);
    return throwError(() => new Error(err.message || 'Server error'));
  }
}
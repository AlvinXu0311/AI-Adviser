import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface ExtractedTranscriptData {
  studentName?: string;
  studentId?: string;
  gpa?: number;
  completedCourses?: CourseInfo[];
  currentCourses?: CourseInfo[];
  programInfo?: ProgramInfo;
  rawText?: string;
}

export interface CourseInfo {
  courseCode: string;
  courseName: string;
  credits: number;
  grade?: string;
  semester?: string;
}

export interface ProgramInfo {
  programName: string;
  enrollmentDate?: Date;
  expectedGraduationDate?: Date;
}

interface ExtractTranscriptResponse {
  success: boolean;
  data?: ExtractedTranscriptData;
  error?: string;
}

@Injectable({
  providedIn: 'root'
})
export class PdfUploadService {
  private transcriptData = new BehaviorSubject<ExtractedTranscriptData | null>(null);
  public transcriptData$ = this.transcriptData.asObservable();

  private apiUrl = 'http://localhost:8000/api/extract-transcript';

  constructor(private http: HttpClient) {}

  /**
   * Upload PDF to backend for processing and extraction
   * The backend handles PDF text extraction using Gemini Vision API
   * and returns structured transcript data
   */
  async uploadAndEncodePDF(file: File): Promise<ExtractedTranscriptData> {
    try {
      console.log('📄 Starting PDF upload process...');
      console.log(`   File name: ${file.name}`);
      console.log(`   File size: ${(file.size / 1024).toFixed(2)} KB`);
      console.log(`   File type: ${file.type}`);

      // Validate file type
      if (!this.isValidPDFFile(file)) {
        throw new Error('Invalid file type. Please upload a PDF file.');
      }

      // Convert file to base64
      console.log('Converting PDF to base64...');
      const base64Content = await this.fileToBase64(file);
      console.log(`Base64 conversion complete. Length: ${base64Content.length} characters`);

      // Send to backend for processing
      console.log('Sending base64 PDF to backend for extraction...');
      return this.sendToBackend(base64Content);
    } catch (error) {
      console.error('Error processing PDF:', error);
      throw error;
    }
  }

  /**
   * Send base64 PDF to backend for extraction and parsing
   */
  private sendToBackend(pdfBase64: string): Promise<ExtractedTranscriptData> {
    return new Promise((resolve, reject) => {
      console.log(`🔗 POST request to: ${this.apiUrl}`);
      console.log(`📦 Request payload size: ${(pdfBase64.length / 1024).toFixed(2)} KB`);

      this.http
        .post<ExtractTranscriptResponse>(this.apiUrl, { pdf_base64: pdfBase64 })
        .subscribe({
          next: (response) => {
            console.log('Response received from backend');
            console.log(`   Success: ${response.success}`);

            if (response.success && response.data) {
              console.log('Extracted Transcript Data:');
              console.log(`   Student Name: ${response.data.studentName || 'N/A'}`);
              console.log(`   Student ID: ${response.data.studentId || 'N/A'}`);
              console.log(`   GPA: ${response.data.gpa || 'N/A'}`);
              console.log(`   Program: ${response.data.programInfo?.programName || 'N/A'}`);
              console.log(`   Completed Courses: ${response.data.completedCourses?.length || 0}`);
              console.log(`   Current Courses: ${response.data.currentCourses?.length || 0}`);

              if (response.data.rawText) {
                console.log(`   Raw Extracted Text Preview (first 500 chars):`);
                console.log(`   ${response.data.rawText.substring(0, 500)}...`);
              }

              this.transcriptData.next(response.data);
              resolve(response.data);
            } else {
              const errorMsg = response.error || 'Failed to extract transcript';
              console.error(`Backend error: ${errorMsg}`);
              reject(new Error(errorMsg));
            }
          },
          error: (error) => {
            console.error('Backend extraction error:', error);
            console.error(`   Status: ${error.status}`);
            console.error(`   Message: ${error.message}`);
            if (error.error) {
              console.error(`   Response: ${JSON.stringify(error.error)}`);
            }
            reject(new Error('Failed to communicate with backend: ' + (error.message || 'Unknown error')));
          }
        });
    });
  }

  /**
   * Convert File to Base64 string for storage/transmission
   */
  private fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const result = reader.result as string;
        // Remove data:application/pdf;base64, prefix
        const base64 = result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = error => reject(error);
    });
  }


  /**
   * Validate PDF file
   */
  private isValidPDFFile(file: File): boolean {
    return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  }

  /**
   * Get current transcript data
   */
  getCurrentTranscriptData(): ExtractedTranscriptData | null {
    return this.transcriptData.getValue();
  }

  /**
   * Clear transcript data
   */
  clearTranscriptData(): void {
    this.transcriptData.next(null);
  }
}

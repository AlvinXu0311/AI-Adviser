import { Component, Output, EventEmitter, OnInit, } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { PdfUploadService, ExtractedTranscriptData } from '../../services/pdf-upload.service';

@Component({
  selector: 'app-pdf-upload',
  templateUrl: './pdf-upload.component.html',
  styleUrls: ['./pdf-upload.component.scss']
})
export class PdfUploadComponent implements OnInit {
  @Output() transcriptLoaded = new EventEmitter<ExtractedTranscriptData>();

  selectedFile: File | null = null;
  isLoading = false;
  uploadSuccess = false;
  uploadError: string | null = null;
  uploadProgress = 0;
  transcriptData: ExtractedTranscriptData | null = null;

  constructor(
    private pdfUploadService: PdfUploadService,
    private dialog: MatDialog
  ) {}

  ngOnInit(): void {
    // Subscribe to transcript data changes
    this.pdfUploadService.transcriptData$.subscribe(data => {
      this.transcriptData = data;
    });
  }

  /**
   * Handle file selection from input
   */
  onFileSelected(event: any): void {
    const file = event.target.files[0];
    if (file) {
      this.selectedFile = file;
      this.uploadError = null;
      this.uploadSuccess = false;
    }
  }

  /**
   * Handle drag and drop events
   */
  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    (event.currentTarget as HTMLElement).classList.add('drag-over');
  }

  onDragLeave(event: DragEvent): void {
    (event.currentTarget as HTMLElement).classList.remove('drag-over');
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    (event.currentTarget as HTMLElement).classList.remove('drag-over');

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.selectedFile = files[0];
      this.uploadError = null;
      this.uploadSuccess = false;
    }
  }

  /**
   * Upload and process PDF
   */
  async uploadPDF(): Promise<void> {
    if (!this.selectedFile) {
      this.uploadError = 'Please select a PDF file first.';
      return;
    }

    this.isLoading = true;
    this.uploadError = null;
    this.uploadSuccess = false;
    this.uploadProgress = 0;

    let progressInterval: any;

    try {
      // Simulate progress
      progressInterval = setInterval(() => {
        if (this.uploadProgress < 90) {
          this.uploadProgress += Math.random() * 30;
        }
      }, 200);

      const result = await this.pdfUploadService.uploadAndEncodePDF(this.selectedFile);

      clearInterval(progressInterval);
      this.uploadProgress = 100;
      this.uploadSuccess = true;
      this.transcriptData = result;
      this.transcriptLoaded.emit(result);

      // Reset after 2 seconds
      setTimeout(() => {
        this.selectedFile = null;
        this.uploadProgress = 0;
        this.isLoading = false;
      }, 2000);

    } catch (error) {
      if (progressInterval) {
        clearInterval(progressInterval);
      }
      this.uploadError = error instanceof Error ? error.message : 'Failed to process PDF file.';
      this.isLoading = false;
      this.uploadProgress = 0;
    }
  }

  /**
   * Clear selected file
   */
  clearSelection(): void {
    this.selectedFile = null;
    this.uploadError = null;
    this.uploadSuccess = false;
    this.uploadProgress = 0;
  }

  /**
   * Get file size in MB
   */
  getFileSizeMB(): string {
    if (!this.selectedFile) return '0';
    return (this.selectedFile.size / (1024 * 1024)).toFixed(2);
  }

  /**
   * Get file name without extension
   */
  getFileName(): string {
    if (!this.selectedFile) return '';
    return this.selectedFile.name.replace(/\.[^/.]+$/, '');
  }

}

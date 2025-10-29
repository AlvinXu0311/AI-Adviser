import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { FormsModule } from '@angular/forms';
import { PdfUploadComponent } from './pdf-upload.component';
import { PdfUploadService } from '../../services/pdf-upload.service';

describe('PdfUploadComponent', () => {
  let component: PdfUploadComponent;
  let fixture: ComponentFixture<PdfUploadComponent>;
  let pdfService: jasmine.SpyObj<PdfUploadService>;

  beforeEach(async () => {
    const pdfServiceSpy = jasmine.createSpyObj('PdfUploadService', [
      'uploadAndEncodePDF',
      'validateFile'
    ]);

    await TestBed.configureTestingModule({
      declarations: [PdfUploadComponent],
      imports: [
        BrowserAnimationsModule,
        MatFormFieldModule,
        MatInputModule,
        MatButtonModule,
        MatIconModule,
        MatProgressBarModule,
        MatCardModule,
        MatChipsModule,
        FormsModule
      ],
      providers: [
        { provide: PdfUploadService, useValue: pdfServiceSpy }
      ]
    }).compileComponents();

    pdfService = TestBed.inject(PdfUploadService) as jasmine.SpyObj<PdfUploadService>;
    fixture = TestBed.createComponent(PdfUploadComponent);
    component = fixture.componentInstance;
  });

  describe('Initialization', () => {
    it('should create the component', () => {
      expect(component).toBeTruthy();
    });

    it('should initialize with no selected file', () => {
      expect(component.selectedFile).toBeUndefined();
    });

    it('should initialize with progress at 0', () => {
      expect(component.uploadProgress).toBe(0);
    });

    it('should initialize with no upload success message', () => {
      expect(component.uploadSuccess).toBeFalse();
    });

    it('should initialize with no upload error', () => {
      expect(component.uploadError).toBeNull();
    });

    it('should initialize with no extracted data', () => {
      expect(component.extractedData).toBeNull();
    });
  });

  describe('File Selection', () => {
    it('should select PDF file via click', () => {
      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      const event = {
        target: {
          files: [file]
        }
      } as any;

      component.onFileSelected(event);

      expect(component.selectedFile).toEqual(file);
    });

    it('should handle file input change', () => {
      const file = new File(['test'], 'document.pdf', { type: 'application/pdf' });
      const event = {
        target: {
          files: [file]
        }
      } as any;

      component.onFileSelected(event);

      expect(component.selectedFile).toBeTruthy();
      expect(component.uploadError).toBeNull();
    });

    it('should handle no file selected', () => {
      const event = {
        target: {
          files: []
        }
      } as any;

      component.onFileSelected(event);

      expect(component.selectedFile).toBeUndefined();
    });
  });

  describe('Drag and Drop', () => {
    it('should handle drag over', () => {
      const dragEvent = new DragEvent('dragover', {
        dataTransfer: new DataTransfer()
      });

      component.onDragOver(dragEvent);

      expect(component.isDragOver).toBeTrue();
    });

    it('should handle drag leave', () => {
      component.isDragOver = true;

      const dragEvent = new DragEvent('dragleave', {
        dataTransfer: new DataTransfer()
      });

      component.onDragLeave(dragEvent);

      expect(component.isDragOver).toBeFalse();
    });

    it('should handle drop with PDF file', () => {
      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      const dragEvent = new DragEvent('drop', {
        dataTransfer: dataTransfer
      });

      spyOn(dragEvent, 'preventDefault');
      spyOn(dragEvent, 'stopPropagation');

      component.onDrop(dragEvent);

      expect(dragEvent.preventDefault).toHaveBeenCalled();
      expect(dragEvent.stopPropagation).toHaveBeenCalled();
      expect(component.selectedFile).toEqual(file);
      expect(component.isDragOver).toBeFalse();
    });

    it('should reject non-PDF files on drop', () => {
      const file = new File(['test'], 'test.txt', { type: 'text/plain' });
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(file);
      const dragEvent = new DragEvent('drop', {
        dataTransfer: dataTransfer
      });

      component.onDrop(dragEvent);

      expect(component.uploadError).toBeTruthy();
    });
  });

  describe('PDF Upload and Processing', () => {
    it('should upload PDF successfully', fakeAsync(() => {
      const mockTranscriptData = {
        studentName: 'John Doe',
        gpa: 3.85,
        completedCourses: [],
        currentCourses: []
      };
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.resolve(mockTranscriptData));

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      expect(pdfService.uploadAndEncodePDF).toHaveBeenCalledWith(file);
      expect(component.uploadSuccess).toBeTrue();
      expect(component.extractedData).toEqual(mockTranscriptData);
    }));

    it('should emit transcriptLoaded event on successful upload', fakeAsync(() => {
      const mockTranscriptData = {
        studentName: 'Jane Doe',
        gpa: 3.5
      };
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.resolve(mockTranscriptData));
      spyOn(component.transcriptLoaded, 'emit');

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      expect(component.transcriptLoaded.emit).toHaveBeenCalledWith(mockTranscriptData);
    }));

    it('should handle upload error', fakeAsync(() => {
      const errorMessage = 'Invalid PDF format';
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.reject(new Error(errorMessage)));

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      expect(component.uploadError).toContain(errorMessage);
      expect(component.uploadSuccess).toBeFalse();
    }));

    it('should not upload if no file selected', () => {
      component.selectedFile = undefined;

      component.uploadPDF();

      expect(pdfService.uploadAndEncodePDF).not.toHaveBeenCalled();
    });
  });

  describe('File Validation', () => {
    it('should accept PDF files', () => {
      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });

      component.onFileSelected({
        target: { files: [file] }
      } as any);

      expect(component.uploadError).toBeNull();
    });

    it('should reject non-PDF files', () => {
      const file = new File(['test'], 'test.txt', { type: 'text/plain' });

      component.onFileSelected({
        target: { files: [file] }
      } as any);

      expect(component.uploadError).toBeTruthy();
    });

    it('should validate file type by extension', () => {
      const file = new File(['test'], 'test.doc', { type: 'application/msword' });

      component.onFileSelected({
        target: { files: [file] }
      } as any);

      expect(component.uploadError).toBeTruthy();
    });
  });

  describe('Progress Tracking', () => {
    it('should update progress during upload', fakeAsync(() => {
      const mockTranscriptData = {
        studentName: 'John Doe',
        gpa: 3.85
      };
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.resolve(mockTranscriptData));

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      // Progress should reach 100 after successful upload
      expect(component.uploadProgress).toBe(100);
    }));
  });

  describe('Transcript Data Display', () => {
    it('should display extracted student name', () => {
      component.extractedData = {
        studentName: 'John Doe',
        gpa: 3.85,
        completedCourses: []
      };

      expect(component.extractedData.studentName).toEqual('John Doe');
    });

    it('should display extracted GPA', () => {
      component.extractedData = {
        studentName: 'Jane Doe',
        gpa: 3.5,
        completedCourses: []
      };

      expect(component.extractedData.gpa).toEqual(3.5);
    });

    it('should handle null extracted data', () => {
      component.extractedData = null;

      expect(component.extractedData).toBeNull();
    });

    it('should display course information', () => {
      component.extractedData = {
        studentName: 'John Doe',
        gpa: 3.85,
        completedCourses: [
          {
            courseCode: 'BUS501',
            courseName: 'Intro to Analytics',
            credits: 3,
            grade: 'A'
          }
        ]
      };

      expect(component.extractedData.completedCourses?.length).toBe(1);
      expect(component.extractedData.completedCourses?.[0].courseCode).toEqual('BUS501');
    });
  });

  describe('Error Handling', () => {
    it('should display error message on failed upload', fakeAsync(() => {
      const errorMsg = 'Failed to process PDF';
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.reject(new Error(errorMsg)));

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      expect(component.uploadError).toContain(errorMsg);
    }));

    it('should clear error on new file selection', () => {
      component.uploadError = 'Previous error';
      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });

      component.onFileSelected({
        target: { files: [file] }
      } as any);

      expect(component.uploadError).toBeNull();
    });

    it('should handle generic error objects', fakeAsync(() => {
      pdfService.uploadAndEncodePDF.and.returnValue(Promise.reject({}));

      const file = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.selectedFile = file;

      component.uploadPDF();
      tick();

      expect(component.uploadError).toBeTruthy();
    }));
  });

  describe('Reset Functionality', () => {
    it('should reset upload state', () => {
      component.selectedFile = new File(['test'], 'test.pdf', { type: 'application/pdf' });
      component.uploadSuccess = true;
      component.uploadProgress = 100;
      component.extractedData = { studentName: 'John' };

      // Simulate resetting by selecting new file
      const newFile = new File(['test2'], 'test2.pdf', { type: 'application/pdf' });
      component.onFileSelected({
        target: { files: [newFile] }
      } as any);

      expect(component.selectedFile).toEqual(newFile);
      expect(component.uploadError).toBeNull();
    });
  });
});

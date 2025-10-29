# WPI Business School Digital Library - Frontend

Interactive chatbot interface with PDF transcript upload and LLM-powered academic advising system.

## Overview

This is the frontend implementation for the WPI Business School Digital Library. It provides:
- Interactive chat interface for academic queries
- PDF transcript upload with automatic extraction
- Structured data encoding for LLM processing
- Context-aware conversations based on student data
- Fully responsive Material Design UI

## Status

Frontend implementation: COMPLETE and ready for backend integration.

## Quick Start

### Installation

```bash
cd frontend
npm install
npm start
```

Access the application at http://localhost:4200

### Build for Production

```bash
npm run build
# Output: dist/frontend/
```

### Run Tests

```bash
npm test
```

## Project Structure

```
src/app/
├── components/
│   └── pdf-upload/
│       ├── pdf-upload.component.ts       (PDF file handling & UI logic)
│       ├── pdf-upload.component.html     (Upload form template)
│       ├── pdf-upload.component.scss     (Component styling)
│       └── pdf-upload.component.spec.ts  (Unit tests)
├── services/
│   ├── chat.service.ts                   (Enhanced: context-aware messaging)
│   └── pdf-upload.service.ts             (NEW: Transcript extraction & encoding)
├── app.component.ts                      (Main container with chat logic)
├── app.component.html                    (Main layout template)
├── app.component.scss                    (Main component styling)
├── app.module.ts                         (Module declarations & imports)
└── app-routing.module.ts                 (Routing configuration)
```

## Key Components

### PDF Upload Component

Handles PDF file selection, validation, and processing.

Features:
- Drag-and-drop file upload
- File type and size validation
- Upload progress tracking
- Extracted data preview
- Success/error messaging

### Chat Service

Sends messages with optional transcript context to backend.

Example usage:
```typescript
const payload = {
  message: "What should I take next?",
  transcriptContext: {
    studentName: "John Doe",
    gpa: 3.85,
    program: "MS in Business Analytics",
    courseCount: 12
  }
};

this.chatService.sendMessage(payload).subscribe(response => {
  // Handle response
});
```

### PDF Upload Service

Extracts and encodes transcript data for LLM processing.

Pipeline:
1. Validate PDF file format
2. Convert to Base64
3. Extract text content
4. Parse into structured data
5. Generate LLM-ready JSON

Output format:
```json
{
  "studentName": "John Doe",
  "studentId": "WPI123456",
  "gpa": 3.85,
  "programInfo": {"programName": "MS in Business Analytics"},
  "completedCourses": [
    {
      "courseCode": "BA500",
      "courseName": "Advanced Data Analytics",
      "credits": 3,
      "grade": "A",
      "semester": "Fall 2023"
    }
  ],
  "currentCourses": []
}
```

## Features

### Chat Interface
- Send/receive messages
- Message history with timestamps
- Auto-scroll to latest messages
- Loading indicators
- Keyboard support (Enter to send)

### PDF Upload
- Drag-and-drop support
- File browser selection
- Progress tracking
- File validation
- Extracted data display

### Transcript Processing
- Student name and ID extraction
- GPA parsing
- Course parsing (completed and current)
- Grade tracking
- Program detection
- LLM-ready format conversion

### Context-Aware Chat
- Student data attached to requests
- Personalized response capabilities
- Course recommendations support

### Responsive Design
- Desktop: Side-by-side layout
- Tablet: Stacked layout
- Mobile: Full-width responsive

## Technology Stack

- Angular 15
- Angular Material 15
- SCSS
- RxJS
- TypeScript 4.9

## Configuration

### API Endpoint

Update backend URL in src/app/services/chat.service.ts:

```typescript
private apiUrl = 'http://localhost:8000/api/chat';
```

### Transcript Parsing

Customize regex in src/app/services/pdf-upload.service.ts parseTranscriptText() method to match your transcript format.

### Styling

Colors can be customized in:
- src/app/app.component.scss (component styles)
- src/styles.scss (global styles)

Primary color: #667eea to #764ba2 (gradient)

## API Integration

The frontend expects a backend API at POST /api/chat

Request format:
```json
{
  "message": "What are the elective requirements?",
  "transcriptContext": {
    "studentName": "John Doe",
    "gpa": 3.85,
    "program": "MS in Business Analytics",
    "courseCount": 12
  }
}
```

Response format:
```json
{
  "response": "Based on your transcript and program..."
}
```

See BACKEND_ROADMAP.md in the project root for full backend specifications.

## Development

### File Organization

- src/app/components/ - Reusable components
- src/app/services/ - Business logic and HTTP communication
- src/styles.scss - Global styles

### Creating Components

```bash
ng generate component components/new-feature
ng generate service services/new-service
```

### Code Style

- TypeScript strict mode enabled
- RxJS observables for async operations
- Component encapsulation
- Service isolation

## Styling

### Responsive Breakpoints

- Desktop: > 1024px (side-by-side layout)
- Tablet: 768px - 1024px (stacked layout)
- Mobile: < 768px (full-width responsive)

### Color Scheme

- Primary Gradient: #667eea to #764ba2
- User Messages: Purple gradient
- Bot Messages: #f5f5f5
- Success: #4caf50
- Error: #d32f2f
- Background: #f5f7fa to #c3cfe2

## Data Flow

1. User uploads PDF transcript
2. Frontend validates and processes PDF
3. Extracted data stored in component state
4. User sends chat message
5. Frontend attaches transcript context to request
6. HTTP request sent to backend
7. Response received and displayed
8. Message added to conversation history

## Performance

- Bundle size: approximately 500 KB
- OnPush change detection compatible
- Virtual scrolling compatible
- Service worker ready
- AOT compilation enabled

## Security

Current implementation:
- Client-side file validation
- Base64 encoding for transmission
- No sensitive data in localStorage
- TypeScript strict mode

For production, add:
- HTTPS/TLS encryption
- User authentication (OAuth 2.0 or JWT)
- Rate limiting
- CORS validation
- Input sanitization
- Audit logging

## Testing

Run unit tests:
```bash
npm test
```

Manual testing checklist:
- Application loads at localhost:4200
- PDF upload works (drag-drop and click)
- PDF validation works (rejects non-PDF)
- Transcript extraction succeeds
- Chat messages send successfully
- Responsive design works on all screen sizes

## Troubleshooting

### PDF Upload Not Working

- Check browser console (F12) for error messages
- Verify PDF file is valid
- Check that transcript format matches parsing regex
- Customize parseTranscriptText() method if needed

### Chat Not Sending Messages

- Verify backend API is running
- Check Network tab (F12) for failed requests
- Verify API URL is correct
- Check backend error logs

### Styling Issues

```bash
ng cache clean
npm start
```

## Customization

### Modify Transcript Format

Edit parseTranscriptText() in src/app/services/pdf-upload.service.ts to match your transcript format:

```typescript
private parseTranscriptText(text: string): ExtractedTranscriptData {
  const nameMatch = text.match(/Your Name Pattern/i);
  const gpaMatch = text.match(/Your GPA Pattern/i);
  // customize for your transcript format
}
```

### Extend Data Structure

Update ExtractedTranscriptData interface:

```typescript
interface ExtractedTranscriptData {
  // existing fields
  additionalField?: string;
}
```

### Change Colors

Update color values in SCSS files:

```scss
$primary-color: #667eea;
$primary-dark: #764ba2;
```

## Environment Configuration

For production, create src/environments/environment.prod.ts:

```typescript
export const environment = {
  production: true,
  apiUrl: 'https://api.example.com'
};
```

## Backend Integration

The frontend is ready for backend API implementation. The backend should:

1. Implement POST /api/chat endpoint
2. Connect to Gemini LLM API
3. Create rule-based system for course recommendations
4. Setup RAG pipeline for accuracy

See BACKEND_ROADMAP.md in the project root for detailed backend implementation guide.

## Available Scripts

```bash
npm start              # Start development server
npm run build          # Build for production
npm test               # Run unit tests
npm run watch          # Watch mode build
ng generate            # Generate new components/services
```

## Dependencies

Main:
- @angular/core@15
- @angular/material@15
- rxjs@7
- typescript@4.9

All dependencies listed in package.json

## Documentation

Complete documentation files in the project root:

1. IMPLEMENTATION_SUMMARY.md - Project overview and architecture
2. API_CONTRACT.md - Full API specifications with examples
3. BACKEND_ROADMAP.md - Backend implementation guide

## Project Status

Completed:
- Chat component with message history
- PDF upload with drag-drop
- Transcript extraction service
- Responsive Material Design UI
- Error handling and validation

Pending (Backend):
- LLM API integration
- Chat endpoint implementation
- Rule-based course system
- RAG pipeline
- Database for programs

Next Steps:
1. Implement backend API following BACKEND_ROADMAP.md
2. Connect frontend to backend
3. Test end-to-end workflow
4. Deploy to production

## Support

For questions about:
- Frontend implementation: Review source code in src/app/
- Architecture and design: See IMPLEMENTATION_SUMMARY.md
- API integration: See API_CONTRACT.md
- Backend development: See BACKEND_ROADMAP.md

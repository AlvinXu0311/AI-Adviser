import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Pipe({
  name: 'formatAnswer'
})
export class FormatAnswerPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {}

  transform(text: string): SafeHtml {
    if (!text) return '';

    // Split by FINAL ANSWER separator
    const parts = text.split(/==================================================\nFINAL ANSWER\n==================================================\n\n/);

    if (parts.length === 2) {
      // We have both thinking process and final answer
      const thinkingProcess = parts[0];
      const finalAnswer = parts[1];

      // Format thinking process (dim/muted)
      const thinkingHtml = `<div class="thinking-process">${this.escapeHtml(thinkingProcess)}</div>`;

      // Format final answer (bold and large)
      const answerHtml = `<div class="final-answer-section">
        <div class="final-answer-label">FINAL ANSWER</div>
        <div class="final-answer-content">${this.escapeHtml(finalAnswer)}</div>
      </div>`;

      return this.sanitizer.bypassSecurityTrustHtml(thinkingHtml + answerHtml);
    } else {
      // No separator found, just format as regular text
      return this.sanitizer.bypassSecurityTrustHtml(`<div class="message-plain">${this.escapeHtml(text)}</div>`);
    }
  }

  private escapeHtml(text: string): string {
    const map: { [key: string]: string } = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
  }
}

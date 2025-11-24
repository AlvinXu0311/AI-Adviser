import { useState, KeyboardEvent, useRef, ChangeEvent, useEffect, FC } from 'react';
import { Send, Paperclip, Mic } from 'lucide-react';

interface InputAreaProps {
  onSendMessage: (text: string) => void;
  onFileUpload: (file: File) => void;
  disabled: boolean;
  placeholder?: string;
}

export const InputArea: FC<InputAreaProps> = ({ onSendMessage, onFileUpload, disabled, placeholder }) => {
  const [input, setInput] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);

  useEffect(() => {
    const supported = typeof window !== 'undefined' && (
      'SpeechRecognition' in (window as any) ||
      'webkitSpeechRecognition' in (window as any)
    );
    setSpeechSupported(supported);

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        recognitionRef.current.stop?.();
      }
    };
  }, []);

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePaperclipClick = () => {
    if (!disabled) {
      fileInputRef.current?.click();
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileUpload(e.target.files[0]);
    }
    // Reset input so the same file can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    if (recognitionRef.current) {
      recognitionRef.current.stop?.();
    }
  };

  const handleMicClick = () => {
    if (disabled || !speechSupported) {
      return;
    }

    if (isRecording) {
      stopRecording();
      return;
    }

    try {
      const SpeechRecognitionCtor = typeof window !== 'undefined'
        ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
        : null;

      if (!SpeechRecognitionCtor) {
        throw new Error('SpeechRecognition API not available');
      }

      const recognition = new SpeechRecognitionCtor();
      recognition.lang = 'en-US';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event: any) => {
        const transcript = event.results?.[0]?.[0]?.transcript || '';
        if (transcript) {
          setInput(prev => (prev ? `${prev} ${transcript}` : transcript));
        }
      };

      recognition.onerror = (event: any) => {
        setSpeechError(event?.error || 'Speech recognition error');
        setIsRecording(false);
      };

      recognition.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = recognition;
      setSpeechError(null);
      setIsRecording(true);
      recognition.start();
    } catch (error) {
      console.error('Speech recognition failed', error);
      setSpeechError('Speech recognition is not supported in this browser.');
      setIsRecording(false);
    }
  };

  return (
    <div className="relative flex flex-col w-full gap-1">
      <div className="flex items-center w-full">
      {/* Hidden File Input */}
      <input 
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        accept=".pdf,.doc,.docx,.jpg,.png,.jpeg"
      />

      <div className="absolute left-2 flex items-center space-x-1">
        <button 
          onClick={handlePaperclipClick}
          className="p-2 text-gray-400 hover:text-wpi-red hover:bg-gray-100 rounded-full transition-colors"
          disabled={disabled}
          title="Upload Transcript"
        >
          <Paperclip size={20} />
        </button>
      </div>
      
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder ?? (disabled ? "Agent is thinking..." : "Ask questions or upload your transcript...")}
        disabled={disabled}
        className="w-full pl-12 pr-14 py-3.5 bg-gray-50 border border-gray-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-wpi-red/20 focus:border-wpi-red transition-all shadow-inner text-sm disabled:opacity-50 disabled:cursor-not-allowed"
      />

      <div className="absolute right-2 flex items-center space-x-1">
        {input.trim() ? (
          <button
            onClick={handleSend}
            disabled={disabled}
            className="p-2 bg-wpi-red text-white rounded-xl shadow-md hover:bg-wpi-redDark hover:shadow-lg transform active:scale-95 transition-all disabled:opacity-50 disabled:transform-none"
          >
            <Send size={18} />
          </button>
        ) : (
          <button 
            onClick={handleMicClick}
            className={`p-2 rounded-full transition-colors ${isRecording ? 'text-wpi-red bg-wpi-red/10' : 'text-gray-400 hover:text-gray-600'}`}
            disabled={disabled || !speechSupported}
            title={speechSupported ? (isRecording ? 'Stop recording' : 'Record a question') : 'Speech recognition not supported in this browser'}
            aria-pressed={isRecording}
          >
            <Mic size={20} />
          </button>
        )}
      </div>
      </div>
      {isRecording && (
        <p className="text-[10px] text-wpi-red font-semibold">Listening… speak naturally in English.</p>
      )}
      {!isRecording && speechError && (
        <p className="text-[10px] text-wpi-red/80">{speechError}</p>
      )}
    </div>
  );
};
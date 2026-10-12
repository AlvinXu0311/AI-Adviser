import { FC, useEffect, useState } from 'react';
import { AgentStep } from '../types';
import { Brain, CheckCircle2, ChevronDown, ChevronRight, Loader2, Sparkles, Wrench } from 'lucide-react';

interface AgentProcessProps {
  steps: AgentStep[];
  isStreaming: boolean;
}

const TOOL_LABELS: Record<string, string> = {
  smart_course_search: 'Course search',
  program_search: 'Program search',
  semantic_search: 'Catalog search',
  degree_progress: 'Degree audit',
  student_context: 'Student transcript',
  business_school_database: 'Database query',
  pdf_context: 'Catalog context',
};

const toolLabel = (tool: string) => TOOL_LABELS[tool] || tool;

// Tool outputs are raw text dumps (section banners, HTML from the catalog); reduce to a readable one-liner
const summarizeOutput = (output: string) =>
  output
    .replace(/<[^>]+>/g, ' ')
    .replace(/=+\s*[A-Z ]+\s*=+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const ToolStep: FC<{ step: Extract<AgentStep, { kind: 'tool' }> }> = ({ step }) => {
  const [expanded, setExpanded] = useState(false);
  const summary = step.output ? summarizeOutput(step.output) : '';
  const isLong = summary.length > 140;

  return (
    <div className="flex items-start gap-2">
      <div className="mt-0.5 flex-shrink-0">
        {step.status === 'running'
          ? <Loader2 size={14} className="text-wpi-red animate-spin" />
          : <Wrench size={14} className="text-gray-400" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-gray-700">
          <span className="font-semibold">{toolLabel(step.tool)}</span>
          {step.input && (
            <code className="ml-2 bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded text-xs font-mono break-all">{step.input}</code>
          )}
        </div>
        {step.status === 'running' && <div className="text-xs text-gray-400 mt-0.5">Searching…</div>}
        {summary && (
          <button
            type="button"
            onClick={() => isLong && setExpanded(!expanded)}
            className={`block text-left text-xs text-gray-500 mt-1 ${isLong ? 'hover:text-gray-700 cursor-pointer' : 'cursor-default'}`}
          >
            {expanded || !isLong ? summary : `${summary.slice(0, 140)}…`}
          </button>
        )}
      </div>
    </div>
  );
};

export const AgentProcess: FC<AgentProcessProps> = ({ steps, isStreaming }) => {
  // Open while the agent is working, collapse once the answer is done
  const [open, setOpen] = useState(isStreaming);
  useEffect(() => {
    setOpen(isStreaming);
  }, [isStreaming]);

  const toolCount = steps.filter(s => s.kind === 'tool').length;
  const current = [...steps].reverse().find(s => s.kind !== 'thought');
  const liveText = () => {
    if (current?.kind === 'tool') {
      return current.status === 'running' ? `Using ${toolLabel(current.tool)}…` : 'Reviewing results and writing the answer…';
    }
    if (current?.kind === 'stage') return `${current.text}…`;
    return 'Thinking…';
  };
  const headerText = isStreaming
    ? liveText()
    : `Reasoned with ${toolCount} tool call${toolCount === 1 ? '' : 's'}`;

  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/80 text-xs sm:text-sm">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-gray-500 hover:text-gray-700"
      >
        {isStreaming
          ? <Loader2 size={16} className="text-wpi-red animate-spin flex-shrink-0" />
          : <CheckCircle2 size={16} className="text-green-500 flex-shrink-0" />}
        <span className="font-semibold uppercase tracking-wider text-xs">Agent Process</span>
        <span className="truncate">· {headerText}</span>
        <span className="ml-auto flex-shrink-0">{open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2.5 border-t border-gray-100">
          {steps.map((step, idx) => {
            if (step.kind === 'tool') return <ToolStep key={idx} step={step} />;
            if (step.kind === 'thought') {
              return (
                <div key={idx} className="flex items-start gap-2">
                  <Brain size={14} className="mt-0.5 text-purple-400 flex-shrink-0" />
                  <p className="text-gray-600 italic">{step.text}</p>
                </div>
              );
            }
            return (
              <div key={idx} className="flex items-start gap-2">
                <Sparkles size={14} className="mt-0.5 text-amber-400 flex-shrink-0" />
                <p className="text-gray-500">{step.text}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

import { Badge } from '@/components/ui/badge';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { ToolUIPart } from 'ai';
import {
  CheckCircleIcon,
  ChevronDownIcon,
  CircleIcon,
  ClockIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  ShieldXIcon,
  WrenchIcon,
  XCircleIcon,
} from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import { CodeBlock } from './code-block';

// Shared types - uses AI SDK's native tool states
export type ToolState = ToolUIPart['state'];

// Shared status badge component
type ToolStatusBadgeProps = {
  state: ToolState;
  className?: string;
};

export const ToolStatusBadge = ({ state, className }: ToolStatusBadgeProps) => {
  const labels: Record<ToolState, string> = {
    'input-streaming': '待機中',
    'input-available': '実行中',
    'output-available': '完了',
    'output-error': 'エラー',
    'output-denied': '拒否',
    'approval-requested': '承認待ち',
    'approval-responded': '処理中',
  };

  const icons: Record<ToolState, ReactNode> = {
    'input-streaming': <CircleIcon className="size-3" />,
    'input-available': <ClockIcon className="size-3 animate-pulse" />,
    'output-available': <CheckCircleIcon className="size-3" />,
    'output-error': <XCircleIcon className="size-3" />,
    'output-denied': <ShieldXIcon className="size-3" />,
    'approval-requested': <ShieldAlertIcon className="size-3" />,
    'approval-responded': <ShieldCheckIcon className="size-3" />,
  };

  const variants: Record<ToolState, string> = {
    'input-streaming':
      'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    'input-available':
      'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
    'output-available':
      'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
    'output-error': 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    'output-denied':
      'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    'approval-requested':
      'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300',
    'approval-responded':
      'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  };

  return (
    <Badge
      className={cn(
        'flex items-center gap-1 rounded-full border-0 font-medium text-xs',
        variants[state],
        className,
      )}
      variant="secondary"
    >
      {icons[state]}
      <span>{labels[state]}</span>
    </Badge>
  );
};

// Shared container component
type ToolContainerProps = ComponentProps<typeof Collapsible>;

export const ToolContainer = ({ className, ...props }: ToolContainerProps) => (
  <Collapsible
    className={cn('not-prose w-full rounded-md border', className)}
    {...props}
  />
);

// Shared collapsible content component
type ToolContentProps = ComponentProps<typeof CollapsibleContent>;

export const ToolContent = ({ className, ...props }: ToolContentProps) => (
  <CollapsibleContent
    className={cn(
      'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 text-popover-foreground outline-hidden data-[state=closed]:animate-out data-[state=open]:animate-in',
      className,
    )}
    {...props}
  />
);

// Shared input component
type ToolInputProps = ComponentProps<'div'> & {
  input: ToolUIPart['input'];
};

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => (
  <div className={cn('space-y-2 overflow-hidden p-3', className)} {...props}>
    <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
      パラメータ
    </h4>
    <div className="rounded-md bg-muted/50">
      <CodeBlock code={JSON.stringify(input, null, 2)} language="json" />
    </div>
  </div>
);

// Shared output component
type ToolOutputProps = ComponentProps<'div'> & {
  output: ReactNode;
  errorText?: string;
};

export const ToolOutput = ({
  className,
  output,
  errorText,
  ...props
}: ToolOutputProps) => {
  if (!(output || errorText)) {
    return null;
  }

  return (
    <div className={cn('space-y-2 p-3', className)} {...props}>
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
        {errorText ? 'エラー' : '結果'}
      </h4>
      <div
        className={cn(
          'overflow-x-auto rounded-md text-xs [&_table]:w-full',
          errorText
            ? 'bg-destructive/10 text-destructive'
            : 'bg-muted/50 text-foreground',
        )}
      >
        {errorText && <div className="p-2">{errorText}</div>}
        {output && <div>{output}</div>}
      </div>
    </div>
  );
};

// Standard tool components (non-MCP)
export const Tool = ToolContainer;

type ToolHeaderProps = {
  type: ToolUIPart['type'] | string;
  state: ToolState;
  className?: string;
};

export const ToolHeader = ({
  className,
  type,
  state,
  ...props
}: ToolHeaderProps) => (
  <CollapsibleTrigger
    className={cn(
      'flex w-full min-w-0 items-center justify-between gap-2 p-3',
      className,
    )}
    {...props}
  >
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <WrenchIcon className="size-4 shrink-0 text-muted-foreground" />
      <span className="truncate font-medium text-sm">{type}</span>
    </div>
    <div className="flex shrink-0 items-center gap-2">
      <ToolStatusBadge state={state} />
      <ChevronDownIcon className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
    </div>
  </CollapsibleTrigger>
);

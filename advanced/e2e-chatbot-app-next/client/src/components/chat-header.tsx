import { useNavigate } from 'react-router-dom';
import { useWindowSize } from 'usehooks-ts';

import { SidebarToggle } from '@/components/sidebar-toggle';
import { Button } from '@/components/ui/button';
import { useSidebar } from './ui/sidebar';
import { PlusIcon, CloudOffIcon, MessageSquareOff } from 'lucide-react';
import { useConfig } from '@/hooks/use-config';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

const DOCS_URL =
  'https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app';

export function ChatHeader() {
  const navigate = useNavigate();
  const { open } = useSidebar();
  const { chatHistoryEnabled, feedbackEnabled } = useConfig();

  const { width: windowWidth } = useWindowSize();

  return (
    <header className="sticky top-0 flex items-center gap-2 bg-background px-2 py-1.5 md:px-2">
      <SidebarToggle />

      {(!open || windowWidth < 768) && (
        <Button
          variant="outline"
          className="order-2 ml-auto h-8 px-2 md:order-1 md:ml-0 md:h-fit md:px-2"
          onClick={() => {
            navigate('/');
          }}
        >
          <PlusIcon />
          <span className="md:sr-only">新しいチャット</span>
        </Button>
      )}

      <div className="ml-auto flex items-center gap-2">
        {!chatHistoryEnabled && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={DOCS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-full bg-muted px-2 py-1 text-muted-foreground text-xs hover:text-foreground"
                >
                  <CloudOffIcon className="h-3 w-3" />
                  <span className="hidden sm:inline">一時保存</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>
                <p>チャット履歴が無効です — 会話は保存されません。詳しくはクリック。</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        {!feedbackEnabled && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href={DOCS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-full bg-muted px-2 py-1 text-muted-foreground text-xs hover:text-foreground"
                >
                  <MessageSquareOff className="h-3 w-3" />
                  <span className="hidden sm:inline">フィードバック無効</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>
                <p>フィードバック送信が無効です。詳しくはクリック。</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
    </header>
  );
}

import { useCallback, useState } from "react";
import { useChatStore } from "../lib/chatStore";
import type { MessageRow } from "../types";

export function useChat() {
  const messages: MessageRow[] = useChatStore((s) => s.messages);
  const activeId = useChatStore((s) => s.activeId);
  const loading = useChatStore((s) => s.loading);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const [error, setError] = useState<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      setError(null);
      try {
        await sendMessage(text.trim());
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [sendMessage]
  );

  return { messages, busy: loading, error, send, activeId };
}

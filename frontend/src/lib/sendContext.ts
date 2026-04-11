import { createContext, useContext } from "react";

import type { TxMessage } from "@/lib/protocol";

export type SendFn = (msg: TxMessage) => void;

export const SendContext = createContext<SendFn>(() => {
  console.warn("[SendContext] No provider - message dropped");
});

export function useSend(): SendFn {
  return useContext(SendContext);
}

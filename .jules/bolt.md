## 2025-02-28 - React.memo for ChatPanel
**Learning:** The ChatPanel streams text rapidly, causing all previous messages in the chat history to re-render constantly. Wrapping the list item component in `React.memo` prevents this specific to the codebase's streaming architecture.
**Action:** Use `React.memo` on list items that are rendered alongside frequently changing state like streaming text.

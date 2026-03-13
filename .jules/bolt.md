## 2025-02-28 - React.memo for ChatPanel
**Learning:** The ChatPanel streams text rapidly, causing all previous messages in the chat history to re-render constantly. Wrapping the list item component in `React.memo` prevents this specific to the codebase's streaming architecture.
**Action:** Use `React.memo` on list items that are rendered alongside frequently changing state like streaming text.

## 2025-03-05 - React.memo for PreviewTile
**Learning:** `MediaPreviewDock` renders video streams. The dock itself can re-render due to store updates but if the `cameraStream` or `screenStream` instances haven't changed, the `PreviewTile` subcomponents can be safely memoized. Re-rendering video elements unnecessarily could cause slight stutters or layout thrashing.
**Action:** Use `React.memo` on subcomponents in docks or panels that receive media streams or complex objects as props to avoid unnecessary DOM updates during parent state changes.

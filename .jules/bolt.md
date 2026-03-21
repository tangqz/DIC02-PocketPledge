## 2025-02-28 - React.memo for ChatPanel
**Learning:** The ChatPanel streams text rapidly, causing all previous messages in the chat history to re-render constantly. Wrapping the list item component in `React.memo` prevents this specific to the codebase's streaming architecture.
**Action:** Use `React.memo` on list items that are rendered alongside frequently changing state like streaming text.

## 2025-03-05 - React.memo for PreviewTile
**Learning:** `MediaPreviewDock` renders video streams. The dock itself can re-render due to store updates but if the `cameraStream` or `screenStream` instances haven't changed, the `PreviewTile` subcomponents can be safely memoized. Re-rendering video elements unnecessarily could cause slight stutters or layout thrashing.
**Action:** Use `React.memo` on subcomponents in docks or panels that receive media streams or complex objects as props to avoid unnecessary DOM updates during parent state changes.

## 2025-03-14 - Asyncio Event Loop Blocking by Synchronous DB calls
**Learning:** In `backend/app/agent/local_client.py`, the `_load_profile_content` function executed a synchronous SQLAlchemy database query directly inside the async `stream_chat` function. This blocks the main Python asyncio event loop, causing all concurrent tasks (like other users' websocket events or tool executions) to stall until the database returns.
**Action:** Wrap synchronous database I/O operations in `asyncio.to_thread` when they must be called from within an `async def` function to maintain the fluency and responsiveness of the async application.

## 2025-03-14 - React.memo and useMemo Micro-optimizations
**Learning:** Attempting to optimize simple array operations (like `.filter().length`) on small data sets (like a daily plan's task list) using `useMemo` is an anti-pattern. The React overhead of dependency checking and memory allocation makes performance *worse* and has no measurable impact.
**Action:** Avoid micro-optimizations. Focus on macro-level optimizations (like unblocking the main thread, caching heavy API calls, or fixing N+1 queries) instead of prematurely optimizing fast, native JavaScript operations.
## 2024-05-24 - React Context and Timer State Propagation
**Learning:** Components subscribing to rapidly updating global state (like `timerSeconds` from a Zustand store) cause their entire sub-tree to re-render constantly. While this is expected for the component displaying the timer, static or independent sibling components in that same layout will also needlessly re-render if they aren't memoized.
**Action:** Always wrap static components or components with their own local state (like `CharitySlider` or `MediaPreviewDock`) in `React.memo` when they are rendered inside a parent layout that is subscribed to a high-frequency state update.

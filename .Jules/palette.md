## 2024-05-16 - Focus Styling on Custom Interactive Elements
**Learning:** Custom interactive elements (like the voice input button and chat send button) use standard `<button>` tags but lack focus states and descriptive `aria-label` attributes.
**Action:** Always ensure any interactive elements that use custom SVG or visual representations instead of text have an `aria-label` applied to them. Ensure `focus-visible:ring-2 focus-visible:ring-accent` classes are applied for keyboard accessibility.

## 2024-03-18 - VoiceInput Accessibility and State Feedback
**Learning:** The VoiceInput toggle button lacked explicit `aria-pressed` state for screen readers to understand it's a toggle, and it appeared interactive even when functionally disabled during a "paused" state.
**Action:** Always include `aria-pressed` for toggle buttons, explicitly set `disabled` attributes when an action cannot be performed, and provide visual feedback (like opacity and cursor changes) for disabled states.

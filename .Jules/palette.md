## 2024-05-16 - Focus Styling on Custom Interactive Elements
**Learning:** Custom interactive elements (like the voice input button and chat send button) use standard `<button>` tags but lack focus states and descriptive `aria-label` attributes.
**Action:** Always ensure any interactive elements that use custom SVG or visual representations instead of text have an `aria-label` applied to them. Ensure `focus-visible:ring-2 focus-visible:ring-accent` classes are applied for keyboard accessibility.

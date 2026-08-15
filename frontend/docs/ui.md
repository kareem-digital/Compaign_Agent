# UI Coding Standards

## Component Library

**Only daisyUI components are permitted for all UI in this project.**

- Always use daisyui skill for any UI component generation.

If a component does not exist in daisyUI, open a discussion before introducing any alternative.

## Date Formatting

All dates must be formatted using **date-fns**. No other date formatting libraries or manual formatting are permitted.

### Format

Dates are displayed in the following format:

```
1st Sep 2025
2nd Aug 2025
3rd Jan 2026
4th Jun 2024
```

### Implementation

Use `format` from `date-fns` with the `do MMM yyyy` format string:

```ts
import { format } from 'date-fns';

format(new Date('2025-09-01'), 'do MMM yyyy'); // "1st Sep 2025"
format(new Date('2025-08-02'), 'do MMM yyyy'); // "2nd Aug 2025"
format(new Date('2026-01-03'), 'do MMM yyyy'); // "3rd Jan 2026"
format(new Date('2024-06-04'), 'do MMM yyyy'); // "4th Jun 2024"
```

This applies everywhere a date is rendered in the UI — workout dates, timestamps, labels, etc.
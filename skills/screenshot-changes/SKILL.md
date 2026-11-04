---
name: screenshot-changes
description: Analyzes git changes on the current branch, determines which UI paths demonstrate those changes, navigates to them in the browser, performs necessary interactions, and captures screenshots. Use when user says "screenshot changes", "capture UI changes", "show me the changes", "visual diff", or "take screenshots of my changes".
---

# screenshot-changes

Automates visual verification of UI changes by analyzing the current git branch, determining affected routes, navigating the running app, and capturing screenshots.

## Prerequisites

- The dev server must be running at `https://1console.local.twilio.com:5173/`
- Chrome must be running with DevTools protocol enabled (chrome-devtools MCP connected)
- The branch must have changes relative to `main`

## Authentication

After navigating to a page, check if the browser was redirected to a login page (URL contains `auth.stage.twilio.com` or `login.stage.twilio.com`). If so:

1. Read credentials from `libs/common-e2e/.env.stage` (or `.env.dev`/`.env.prod` depending on environment)
2. Fill the email field and click **Continue**
3. Wait for the password field to appear (the login flow is two-step)
4. Fill the password field and click **Continue**
5. Wait for the redirect back to the original destination URL

## Steps

### Step 1: Analyze git changes

Run `git diff main --name-only` and `git diff main --stat` to identify changed files.

Categorize changes into:
- **Route files** (`apps/console-core/src/routes/**/index.tsx`, `layout.tsx`) - these map directly to URL paths
- **Page components** (`console-app-modules/*/src/pages/**`) - identify which route renders them
- **Shared components** (`libs/`, `console-app-modules/*/src/modules/shared/`) - trace which pages import them
- **Query files** (`console-app-modules/*/src/queries/`) - trace which pages use these queries
- **Layout changes** (`**/layout.tsx`, `**/shell/**`, `**/breadcrumbs/**`) - affect multiple pages, screenshot representative samples
- **Locale/i18n changes** (`**/locales/**/*.json`) - identify which keys changed and which components reference them

### Step 2: Map changes to UI paths

For each changed file, determine the URL path(s) needed to observe the change:

**Route-to-URL mapping convention:**
```
apps/console-core/src/routes/account/[accountSid]/[region]/<module-path>/index.tsx
  -> https://1console.local.twilio.com:5173/account/<accountSid>/<region>/<module-path>
```

The `accountSid` and `region` values can be found in `libs/common-e2e/.env.stage` (or `.env.dev`/`.env.prod` depending on environment). Example:
```
https://1console.local.twilio.com:5173/account/<accountSid>/us1/customer-memory/stores
```

Dynamic segments like `[storeId]`, `[profileId]` must be discovered by navigating to a parent listing page first and clicking into an item.

**Tracing non-route changes:**
- For page components: find the route file that imports or lazy-loads the component
- For shared modules: search for imports across page components, then find their routes
- For layout changes: identify all child routes affected, pick representative pages
- For locale changes: grep the changed i18n keys in TSX files to find consuming components

### Step 3: Plan screenshot scenarios

For each UI path, determine what interactions are needed to demonstrate the change:

| Change Type | Interaction Pattern |
|---|---|
| New/modified page content | Navigate to page, wait for load, screenshot |
| Layout/breadcrumb changes | Navigate to multiple nested pages, screenshot each |
| Form changes | Navigate, fill fields, screenshot before/after |
| Modal/dialog changes | Navigate, click trigger, wait for modal, screenshot |
| Dropdown/popover changes | Navigate, click trigger, wait for popover, screenshot |
| Table/list changes | Navigate, wait for data load, screenshot |
| Settings/config changes | Navigate to settings page, screenshot |
| Error state changes | Navigate, trigger error condition if possible, screenshot |

### Step 4: Create screenshot directory

Create a subdirectory under `screenshots/` in the project root:

```
screenshots/<YYYY-MM-DD>-<short-description>/
```

Where `<short-description>` is a kebab-case summary of the feature (derived from the branch name or dominant change theme). Example: `screenshots/2026-03-06-breadcrumbs-switcher/`

### Step 5: Capture screenshots

For each planned scenario, execute this sequence using chrome-devtools MCP tools:

1. **Navigate**: `mcp__chrome-devtools__navigate_page` to the target URL
2. **Wait**: `mcp__chrome-devtools__wait_for` for key content text to appear (page title, data labels, etc.)
3. **Interact** (if needed):
   - `mcp__chrome-devtools__take_snapshot` to get the a11y tree with element UIDs
   - `mcp__chrome-devtools__click` on trigger elements (buttons, dropdowns, tabs)
   - `mcp__chrome-devtools__wait_for` for resulting content (modals, popovers, expanded sections)
4. **Screenshot**: `mcp__chrome-devtools__take_screenshot` with a descriptive filename
   - Use `savePath` pointing to the screenshot directory created in Step 4
   - Use descriptive filenames: `<page-name>-<state>.png` (e.g., `store-detail-breadcrumb.png`, `store-switcher-open.png`)

### Step 6: Verify and summarize

After all screenshots are captured:

1. Read each screenshot file to visually verify it captured the intended UI state
2. Output a summary table:

```
| Screenshot | URL | Description |
|---|---|---|
| store-detail-breadcrumb.png | /console/customer-memory/stores/ST123 | Breadcrumb navigation on store detail page |
| store-switcher-open.png | /console/customer-memory/stores/ST123 | Store switcher dropdown expanded |
```

## Tips

- After navigation, take a snapshot to check if you landed on a login page — if so, follow the Authentication section above
- For changes that affect multiple modules, group screenshots by module
- If a route requires dynamic IDs (store IDs, profile IDs), navigate to the listing page first and click into the first available item
- Use `mcp__chrome-devtools__list_console_messages` to check for errors after navigation — if errors appear, note them in the summary
- For responsive/layout changes, consider using `mcp__chrome-devtools__resize_page` to capture at different viewport sizes

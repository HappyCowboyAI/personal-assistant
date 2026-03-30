# Backstory Presentation Skill

> Complete reference for creating Backstory branded presentations in PPTX format using pptxgenjs.

**Version:** 2.0
**Last Updated:** March 2026 — Updated for v2.0 brand guidelines (revised color palette, new typography system with LL Kleisch / KMR Waldenburg / Chivo Mono, updated color tokens)

---

## Table of Contents

1. [Overview](#overview)
2. [Brand Colors](#brand-colors)
3. [Typography System](#typography-system)
4. [Text Tier Specifications](#text-tier-specifications)
5. [Column Layout Specifications](#column-layout-specifications)
6. [Logo & Icon Usage](#logo--icon-usage)
7. [Background Elements](#background-elements)
8. [Slide Templates](#slide-templates)
9. [Implementation Patterns](#implementation-patterns)
10. [Asset Inventory](#asset-inventory)
11. [Code Reference](#code-reference)

---

## Overview

This skill creates professional presentations using **Backstory brand guidelines**. Output format is PPTX, editable in Google Slides, PowerPoint, and Keynote.

### Key Specifications

| Property | Value |
|----------|-------|
| Aspect Ratio | 16:9 |
| Dimensions | 10" Ã— 5.625" (pptxgenjs default) |
| Layout | `LAYOUT_16x9` |

### Design Principles

- Clean, professional layouts with generous whitespace
- Solid color or gradient backgrounds (no busy patterns)
- Consistent use of brand colors for visual hierarchy
- Headlines in serif font (LL Kleisch Light; fallback: Cardo), body in sans-serif (KMR Waldenburg; fallback: Roboto)
- Data labels and stat values in monospaced font (Chivo Mono)
- Single text blocks for bulleted lists (not individual text boxes)

---

## Brand Colors

> **Updated March 2026** — v2.0 brand guidelines. Color values sourced from Figma design token primitives. Key changes from v1.1: Horizon, Mint, and Indigo hex values updated; color names standardized.

### Color Hierarchy

| Weight | Colors | Usage |
|--------|--------|-------|
| **Neutral (dominant)** | Black, White | Primary visual language — always lead with these |
| **Primary (supporting)** | Graphite, Surface Gray, Horizon | Structure, hierarchy, secondary surfaces |
| **Secondary (accent only)** | Plum, Mint, Cinder, Indigo, Cobalt | Used sparingly; never competing with content |

### Primary Palette

| Name | HEX | RGB | Usage |
|------|-----|-----|-------|
| **Black** | `#000000` | 0/0/0 | Primary text on light backgrounds |
| **Graphite** | `#171721` | 23/23/33 | Dark backgrounds, secondary text |
| **Graphite 40** | `#55555E` | 85/85/94 | Secondary/supporting text, mid-tone UI |
| **Surface Gray** | `#BBBCBC` | 187/188/188 | Neutral backgrounds, dividers |
| **Horizon** | `#6296AD` | 98/150/173 | Accent color, positive indicators |
| **White** | `#FFFFFF` | 255/255/255 | Light backgrounds, text on dark |

### Secondary Palette

| Name | HEX | RGB | Notes |
|------|-----|-----|-------|
| **Plum** | `#B08FA2` | 176/143/162 | Accent cards, tertiary data series |
| **Mint** | `#8FCDA8` | 143/205/168 | Highlights, success indicators (v2.0: lighter, cooler than v1.1 `#5BA779`) |
| **Cinder** | `#C05527` | 192/85/39 | Warnings, accent cards |
| **Indigo** | `#275198` | 39/81/152 | Accent lines, highlights, dark emphasis (v2.0: significantly darker than v1.1 `#517AC1`) |
| **Cobalt** | `#21B5FF` | 33/181/255 | Links, highlights |
| **Salmon** | `#E8A090` | 232/160/144 | Color stripe accent |
| **Navy** | `#012C48` | 1/44/72 | Dark backgrounds, stat values |

### Color Code (pptxgenjs format — no # prefix)

```javascript
const COLORS = {
    // Neutrals (dominant)
    black:        "000000",
    white:        "FFFFFF",

    // Primary palette (supporting)
    graphite:     "171721",
    graphite40:   "55555E",   // Text/Secondary token
    surfaceGray:  "BBBCBC",
    horizon:      "6296AD",   // v2.0: was 6397AD in v1.1

    // Secondary palette (accent only)
    plum:         "B08FA2",
    mint:         "8FCDA8",   // v2.0: was 5BA779 in v1.1 — lighter, cooler
    cinder:       "C05527",
    indigo:       "275198",   // v2.0: was 517AC1 in v1.1 — significantly darker
    cobalt:       "21B5FF",
    salmon:       "E8A090",   // Color stripe only
    navy:         "012C48"    // Stat values
};
```

### Approved Color Combinations

| Background | Text / Foreground | Type |
|------------|-------------------|------|
| White | Black | Primary |
| Black | White | Primary |
| Graphite | White | Primary |
| Horizon | Black | Accent |
| Plum | Black | Secondary |
| Cinder | White | Secondary |
| Indigo | White | Secondary |
| Cobalt | Black | Secondary |
| Mint | Black | Secondary |

---

## Typography System

> **v2.0 Change** — Type system updated. Three typefaces with distinct roles. PPTX uses fallback fonts unless brand fonts are embedded.

### Font Families

| Brand Typeface | Role | PPTX Fallback | Notes |
|---------------|------|---------------|-------|
| **LL Kleisch Light** | Headlines, display, pull quotes | `"Cardo"` | Embed LL Kleisch if licensed |
| **KMR Waldenburg Regular** | Body, UI, labels, captions, buttons | `"Roboto"` | Embed KMR Waldenburg if licensed |
| **Chivo Mono** | Data labels, stat values, figures, taglines | `"Chivo Mono"` | Available on Google Fonts — embed directly |

### Font Weights

| Usage | Weight | pptxgenjs Property |
|-------|--------|-------------------|
| Headlines | Light (LL Kleisch) / Bold (Cardo fallback) | `bold: true` |
| Subtitles | Regular | `bold: false` |
| Body Text | Regular | `bold: false` |
| Emphasis | Bold | `bold: true` |
| Data / Figures | Regular (Chivo Mono) | `bold: false` |

### Headline Sizes by Slide Type

| Slide Type | Font Size | Font |
|------------|-----------|------|
| Title Slide | 48-72pt | Cardo Bold (or LL Kleisch Light) |
| Section Divider | 40-64pt | Cardo Bold (or LL Kleisch Light) |
| Content Slide Title | 32-44pt | Cardo Bold (or LL Kleisch Light) |
| Subtitle | 18-28pt | Cardo Italic or Roboto (or KMR Waldenburg) |
| Stat Values | 36-60pt | **Chivo Mono Regular** |
| Data Labels | 14-20pt | **Chivo Mono Regular** |

---

## Text Tier Specifications

### Full-Width Body Text (Style Guide Reference)

These are the canonical specifications for full-width content areas:

| Tier | Font Size | Bullet | Unicode | Indent | Para Space Above | Para Space Below |
|------|-----------|--------|---------|--------|------------------|------------------|
| **1st** | 36pt | â— | U+25CF | 0 | 24pt | 12pt |
| **2nd** | 34pt | â€“ | U+2013 | 0.9" | 8pt | 8pt |
| **3rd** | 32pt | â–ª | U+25AA | 1.35" | 8pt | 8pt |

### Scaled Sizes for Column Layouts

When content appears in columns, scale proportionally:

| Layout | Tier 1 | Tier 2 | Tier 3 |
|--------|--------|--------|--------|
| Full-width | 36pt | 34pt | 32pt |
| 2-column | 16-18pt | 14-16pt | 12-14pt |
| 3-column | 14-16pt | 12-14pt | 10-12pt |
| 4-column | 12-14pt | 10-12pt | 8-10pt |

### Bullet Code Reference (pptxgenjs)

```javascript
// Tier 1: Round bullet â—
bullet: { code: "25CF" }

// Tier 2: N-dash â€“
bullet: { code: "2013" }

// Tier 3: Small square â–ª
bullet: { code: "25AA" }
```

---

## Column Layout Specifications

### Subtitle Font Sizes

| Layout | Subtitle Size | Notes |
|--------|---------------|-------|
| 2-column | 30pt | Headers like "Key Wins", "Challenges" |
| 3-column | 28pt | Card titles, section headers |
| 4-column | 22pt | Compact headers |

### Column Widths (10" slide width)

| Layout | Column Width | Gap | Margins |
|--------|--------------|-----|---------|
| 2-column | ~4.2" each | 0.5" | 0.5" left/right |
| 3-column | ~2.4" each | 0.3" | 0.5" left/right |
| 4-column | ~1.8" each | 0.15" | 0.5" left/right |

---

## Logo & Icon Usage

### Available Assets

| Asset | File | Dimensions | Aspect Ratio | Use On |
|-------|------|------------|--------------|--------|
| Wordmark (dark) | `wordmark-dark.png` | 1169×196 | 5.96:1 | Light backgrounds |
| Books Icon (dark) | `books-icon-dark.png` | 628×498 | 1.26:1 | Light backgrounds |
| Books Icon (white) | `books-icon-white.png` | 628×498 | 1.26:1 | Dark backgrounds |
| Building Icon (dark) | `building-icon-dark.png` | 352×495 | 0.71:1 | Light backgrounds — portrait, use for org/team slides |
| Building Icon (white) | `building-icon-white.png` | 352×495 | 0.71:1 | Dark backgrounds — portrait |
| Gradient Stripe | `gradient-stripe.png` | 200×1080 | 0.185:1 | Right edge accent |

> **When to use which icon:** Use the **books icon** on standard content and data slides. Use the **building icon** on people/org slides (bios, team, account overviews) or when the building icon better matches the slide topic.

### Logo Placement Guidelines

**Wordmark Logo:**
- Position: Centered or lower-center on title/section slides
- Typical size: `w: 3.0", h: 0.5"` (maintains 5.96:1 ratio)
- Example: `x: 3.5, y: 3.4, w: 3.0, h: 0.5`

**Books Icon (content slides):**
- Position: Lower-right corner
- Typical size: `w: 0.7", h: 0.55"` (maintains 1.26:1 ratio)
- Example: `x: 8.85, y: 4.65, w: 0.7, h: 0.55`

**Building Icon (people/org slides):**
- Position: Lower-right corner (slightly narrower than books icon)
- Typical size: `w: 0.5", h: 0.7"` (maintains 0.71:1 portrait ratio)
- Example on light bg: `x: 8.9, y: 4.4, w: 0.5, h: 0.7`
- Example on dark panel: `x: 8.6, y: 4.4, w: 0.5, h: 0.7`

**Books/Building Icon (on gradient stripe):**
- Position: Lower portion of stripe
- Books: `x: 8.55, y: 4.55, w: 0.7, h: 0.55`
- Building: `x: 8.6, y: 4.4, w: 0.5, h: 0.7`

### CRITICAL: Aspect Ratio Preservation

Always maintain original aspect ratios:

```javascript
// WRONG — Building icon rendered as square
slide.addImage({ data: buildingIconBase64, x: 8.5, y: 4.4, w: 0.6, h: 0.6 });

// CORRECT — Building icon preserves 0.71:1 portrait ratio
slide.addImage({ data: buildingIconBase64, x: 8.9, y: 4.4, w: 0.5, h: 0.7 });

// CORRECT — Books icon preserves 1.26:1 landscape ratio
slide.addImage({ data: booksIconBase64, x: 8.85, y: 4.65, w: 0.7, h: 0.55 });
```

---

## Background Elements

### Color Stripe (Title/Section Slides)

A horizontal multi-color stripe at the bottom of title and section slides.

```javascript
function addColorStripe(slide, y = 5.1) {
    const stripeColors = [COLORS.surfaceGray, COLORS.plum, COLORS.horizon, COLORS.salmon, COLORS.surfaceGray];  // Surface Gray → Plum → Horizon → Salmon → Surface Gray
    stripeColors.forEach((color, i) => {
        slide.addShape("rect", {
            x: i * 2, y: y, w: 2, h: 0.525,
            fill: { color: color },
            line: { color: color, width: 0 }
        });
    });
}
```

### Gradient Stripe (Content Slides with Cards)

A vertical gradient stripe on the right edge, transitioning from Surface Gray to Graphite.

**Implementation:** Use a pre-generated gradient image for smooth transitions.

```javascript
// Create gradient image (ImageMagick):
// convert -size 200x1080 gradient:"#BBBCBC"-"#171721" gradient-stripe.png

function addNavyStripe(slide) {
    // Add gradient stripe image
    slide.addImage({ 
        data: gradientStripeBase64, 
        x: 8.2, y: 0, w: 1.8, h: 5.625 
    });
    
    // Add white books icon
    slide.addImage({ 
        data: booksIconWhiteBase64, 
        x: 8.55, y: 4.55, w: 0.7, h: 0.55 
    });
}
```

**Why use an image instead of programmatic gradient:**
- pptxgenjs gradient support creates visible banding
- Image-based gradient is perfectly smooth
- Consistent rendering across all viewers

### Rounded Border Frame

For content slides without the gradient stripe:

```javascript
function addFrame(slide) {
    slide.addShape("roundRect", {
        x: 0.2, y: 0.2, w: 9.6, h: 5.2,
        fill: { type: "none" },
        line: { color: COLORS.graphite, width: 2 },
        rectRadius: 0.3
    });
}
```

---

## Slide Templates

### 1. Title Slide

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:1.4, w:9, h:1.2 | 48-72pt | Cardo Bold | Black |
| Subtitle | x:0.5, y:2.6, w:9, h:0.6 | 18-28pt | Cardo Italic | Graphite |
| Logo | x:3.5, y:3.4, w:3.0, h:0.5 | â€” | â€” | â€” |
| Color Stripe | y:5.1, h:0.525 | â€” | â€” | Multi |

### 2. Section Divider

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:2.0, w:9, h:1.2 | 40-64pt | Cardo Bold | Black |
| Logo | x:3.5, y:3.8, w:3.0, h:0.5 | â€” | â€” | â€” |
| Color Stripe | y:5.1, h:0.525 | â€” | â€” | Multi |

### 3. Content with Frame

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Frame | x:0.2, y:0.2, w:9.6, h:5.2 | â€” | â€” | Graphite |
| Title | x:0.5, y:0.5, w:8, h:0.8 | 32-44pt | Cardo Bold | Black |
| Body Area | x:0.5, y:1.5, w:8.5, h:3.5 | varies | Roboto | Graphite |
| Books Icon | x:8.85, y:4.65, w:0.7, h:0.55 | â€” | â€” | â€” |

### 4. Two-Column Layout

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:0.4, w:8, h:0.8 | 32-44pt | Cardo Bold | Black |
| Left Header | x:0.5, y:1.3, w:4.2, h:0.5 | 26pt | Roboto Bold | Horizon/Accent |
| Left Content | x:0.5, y:1.85, w:4.2, h:3.5 | 16pt | Roboto | Graphite |
| Right Header | x:5.2, y:1.3, w:4.2, h:0.5 | 26pt | Roboto Bold | Ember/Accent |
| Right Content | x:5.2, y:1.85, w:4.2, h:3.5 | 16pt | Roboto | Graphite |
| Books Icon | x:8.85, y:4.65, w:0.7, h:0.55 | â€” | â€” | â€” |

### 5. Three-Column Cards (with Gradient Stripe)

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:0.4, w:7, h:0.8 | 32-44pt | Cardo Bold | Black |
| Card 1 | x:0.5, y:1.4, w:2.4, h:3.5 | â€” | â€” | Horizon |
| Card 2 | x:3.0, y:1.4, w:2.4, h:3.5 | â€” | â€” | Plum |
| Card 3 | x:5.5, y:1.4, w:2.4, h:3.5 | â€” | â€” | Ember |
| Card Title | +0.15 from card x | 18-28pt | Roboto Bold | White |
| Card Items | +0.15 from card x | 12-16pt | Roboto | White |
| Gradient Stripe | x:8.2, y:0, w:1.8, h:5.625 | â€” | â€” | Gradient |

### 6. Four-Column Timeline (with Gradient Stripe)

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:0.4, w:7, h:0.8 | 32-44pt | Cardo Bold | Black |
| Q Labels | y:1.3, h:0.4 | 22pt | Roboto Bold | Black |
| Cards | y:1.75, w:1.8, h:3.0 | â€” | â€” | Various |
| Card Focus | center aligned | 18-28pt | Cardo Bold | White |
| Card Sub | center aligned | 14-22pt | Roboto | White |
| Gradient Stripe | x:8.2, y:0, w:1.8, h:5.625 | â€” | â€” | Gradient |

### 7. Stats Dashboard

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:0.5, w:8, h:0.8 | 32-44pt | Cardo Bold | Black |
| Stat Value | w:2.5, h:1.0 | 36-60pt | **Chivo Mono Regular** | Navy |
| Stat Label | w:2.5, h:0.4 | 14-20pt | Roboto | Graphite |
| Stat Change | w:2.5, h:0.4 | 16pt | Roboto Bold | Green (#2E7D32) |
| Books Icon | x:8.85, y:4.65, w:0.7, h:0.55 | â€” | â€” | â€” |

### 8. Thank You Slide

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:1.8, w:9, h:1.5 | 48-80pt | Cardo Bold | Black |
| Subtitle | x:0.5, y:3.3, w:9, h:0.6 | 18-24pt | Roboto | Graphite |
| Logo | x:3.5, y:3.5, w:3.0, h:0.5 | â€” | â€” | â€” |
| Color Stripe | y:5.1, h:0.525 | â€” | â€” | Multi |

### 9. Dark Cover / Section Divider — NEW

Full Graphite background with centered title and Indigo accent line. Use as a dark-theme alternative to the standard white section slide.

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Background | — | Full slide | — | Graphite |
| Title | x:0.75, y:1.6, w:8.5, h:1.2 | 40-64pt | Cardo Bold | White |
| Subtitle | x:0.75, y:2.85, w:8.5, h:0.6 | 16-24pt | Roboto | Surface Gray |
| Indigo Line | x:3.5, y:3.5, w:3.0, h:0.04 | — | — | Indigo |
| Logo | x:3.5, y:4.2, w:3.0, h:0.5 | — | — | — |

```javascript
// Dark cover slide pattern
slide.background = { color: COLORS.graphite };
slide.addText(title, { fontFace: "Cardo", bold: true, color: COLORS.white, align: "center" });
slide.addText(subtitle, { fontFace: "Roboto", color: COLORS.surfaceGray, align: "center" });
slide.addShape("rect", { x: 3.5, y: 3.5, w: 3.0, h: 0.04,
    fill: { color: COLORS.indigo }, line: { color: COLORS.indigo, width: 0 } });
```

### 10. Photo + Text Panel — NEW

Split layout: left text panel (~55%) + right full-bleed photo panel (~45%). Use for speaker bios, case studies, customer spotlights. Use the building icon (white) in the lower-right of the dark panel.

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Title | x:0.5, y:0.4, w:4.5, h:0.8 | 24-36pt | Cardo Bold | Black |
| Person Name | x:0.5, y:1.4, w:4.5, h:0.6 | 28pt | Cardo Bold | Navy |
| Person Title | x:0.5, y:2.05, w:4.5, h:0.4 | 18pt | Roboto | **Indigo** |
| Indigo Line | x:0.5, y:2.5, w:1.5, h:0.04 | — | — | Indigo |
| Bio Bullets | x:0.5, y:2.7, w:4.5, h:2.0 | 16pt | Roboto | Graphite |
| Photo Panel | x:5.3, y:0, w:4.7, h:5.625 | Full height | — | Graphite bg |
| Building Icon (white) | x:8.6, y:4.4, w:0.5, h:0.7 | — | — | White |

### 11. Indigo Accent Stats — NEW

Variant of the Stats Dashboard using Indigo accent bars above each stat and Graphite 40 for labels.

| Element | Position | Size | Font | Color |
|---------|----------|------|------|-------|
| Frame | x:0.2, y:0.2, w:9.6, h:5.2 | — | — | Graphite |
| Title | x:0.5, y:0.5, w:8, h:0.8 | 32-44pt | Cardo Bold | Black |
| Indigo Accent Bar | above each stat, w:1.5, h:0.06 | — | — | **Indigo** |
| Stat Value | w:2.5, h:1.0 | 36-60pt | **Chivo Mono Regular** | Navy |
| Stat Label | w:2.5, h:0.4 | 14-20pt | Roboto | **Graphite 40** |
| Stat Change | w:2.5, h:0.4 | 14pt | Roboto Bold | Green (#2E7D32) or Indigo |


---

## Implementation Patterns

### Pattern 1: Single Text Block for Bulleted Lists

**CRITICAL:** Always use a single text block with `indentLevel` for bulleted lists. Never create separate text boxes for each bullet item.

**Why:**
- PowerPoint handles line wrapping automatically
- Proper spacing between items
- Correct indentation for sub-bullets
- No text overlap issues

```javascript
// CORRECT: Single text block with bullet levels
const bulletedText = [
    { text: "First tier item", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Second tier sub-item", options: { bullet: { code: "2013" }, indentLevel: 1 } },
    { text: "Another first tier item", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Third tier detail", options: { bullet: { code: "25AA" }, indentLevel: 2 } }
];

slide.addText(bulletedText, {
    x: 0.5, y: 1.5, w: 4.2, h: 3.5,
    fontSize: 16, 
    fontFace: "Roboto",
    color: COLORS.graphite,
    valign: "top",
    paraSpaceAfter: 6
});

// WRONG: Separate text boxes (causes overlap)
items.forEach((item, i) => {
    slide.addText(item.text, {
        x: 0.5, y: 1.5 + (i * 0.4), w: 4.2, h: 0.4,
        fontSize: 16
    });
});
```

### Pattern 2: Auto-Sizing Font for Dynamic Content

When content length varies, calculate appropriate font size:

```javascript
function calcFontSize(text, maxWidth, maxFontSize, minFontSize = 12) {
    const charWidthRatio = 0.7; // Conservative for mixed fonts
    const fittedSize = (maxWidth * 72) / (text.length * charWidthRatio);
    return Math.max(minFontSize, Math.min(maxFontSize, Math.floor(fittedSize)));
}

// Usage
const title = "Q4 Performance Highlights";
const fontSize = calcFontSize(title, 8, 44, 32); // Max 44pt, min 32pt, 8" width
```

### Pattern 3: Card Components

For colored card layouts:

```javascript
function addCard(slide, x, y, w, h, color, title, items) {
    // Card background
    slide.addShape("roundRect", {
        x: x, y: y, w: w, h: h,
        fill: { color: color },
        line: { color: color, width: 0 },
        rectRadius: 0.15
    });
    
    // Card title
    slide.addText(title, {
        x: x + 0.15, y: y + 0.15, w: w - 0.3, h: 0.5,
        fontSize: 18, fontFace: "Roboto", bold: true, color: COLORS.white
    });
    
    // Card items as single text block
    const itemsText = items.map(item => ({
        text: item,
        options: { bullet: { code: "25CF" }, indentLevel: 0 }
    }));
    
    slide.addText(itemsText, {
        x: x + 0.15, y: y + 0.7, w: w - 0.3, h: h - 0.9,
        fontSize: 14, fontFace: "Roboto", color: COLORS.white,
        valign: "top"
    });
}
```

### Pattern 4: Loading Images as Base64

```javascript
const fs = require("fs");
const path = require("path");

function imageToBase64(imagePath) {
    try {
        const absolutePath = path.resolve(imagePath);
        const imageBuffer = fs.readFileSync(absolutePath);
        const ext = path.extname(imagePath).toLowerCase().replace('.', '');
        const mimeType = ext === 'jpg' ? 'jpeg' : ext;
        return `data:image/${mimeType};base64,${imageBuffer.toString('base64')}`;
    } catch (err) {
        console.error(`Could not load image: ${imagePath}`, err.message);
        return null;
    }
}

// Load at script initialization
const logoBase64 = imageToBase64("./assets/wordmark-dark.png");
const booksIconBase64 = imageToBase64("./assets/books-icon-dark.png");
```

---

## Asset Inventory

### Required Assets (Transparent PNGs)

| Asset | Filename | Source | Notes |
|-------|----------|--------|-------|
| Wordmark (dark) | `wordmark-dark.png` | Extracted from template PPTX | 1169×196, transparent |
| Books Icon (dark) | `books-icon-dark.png` | Extracted from template PPTX | 628×498, transparent |
| Books Icon (white) | `books-icon-white.png` | Extracted from template PPTX | 628×498, transparent |
| Building Icon (dark) | `building-icon-dark.png` | Extracted from master template | 352×495, transparent — NEW |
| Building Icon (white) | `building-icon-white.png` | Extracted from master template | 352×495, transparent — NEW |
| Gradient Stripe | `gradient-stripe.png` | Generated via ImageMagick | 200×1080, smooth gradient |

### Generating the Gradient Stripe

```bash
convert -size 200x1080 gradient:"#BBBCBC"-"#171721" gradient-stripe.png
```

### Extracting Assets from Template PPTX

```bash
# PPTX files are ZIP archives
unzip -o template.pptx "ppt/media/*" -d ./extracted/

# Check image properties
identify -verbose extracted/ppt/media/image1.png

# Verify transparency
convert image.png -format "Corner: %[pixel:p{0,0}]" info:
# Should show: srgba(0,0,0,0) for transparent
```

---

## Code Reference

### Complete Script Structure

```javascript
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// ============ BRAND CONSTANTS ============
const COLORS = { /* see Brand Colors section */ };
const FONTS = {
    headline: "Cardo",       // Fallback for LL Kleisch Light
    body: "Roboto",          // Fallback for KMR Waldenburg Regular
    data: "Chivo Mono"       // Data labels, stat values, figures
};
const TEXT_STYLES = {
    tier1: { fontSize: 36, bullet: { code: "25CF" }, indentLevel: 0 },
    tier2: { fontSize: 34, bullet: { code: "2013" }, indentLevel: 1 },
    tier3: { fontSize: 32, bullet: { code: "25AA" }, indentLevel: 2 },
    col2Subtitle: { fontSize: 30 },
    col3Subtitle: { fontSize: 28 },
    col4Subtitle: { fontSize: 22 }
};

// ============ PRESENTATION SETUP ============
let pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Backstory";
pres.title = "Presentation Title";

// ============ HELPER FUNCTIONS ============
function imageToBase64(imagePath) { /* ... */ }
function calcFontSize(text, maxWidth, maxFontSize, minFontSize) { /* ... */ }
function addColorStripe(slide, y) { /* ... */ }
function addNavyStripe(slide) { /* ... */ }
function addBooksIcon(slide, x, y, w, h) { /* ... */ }
function addLogo(slide, x, y, w, h) { /* ... */ }
function addFrame(slide) { /* ... */ }

// ============ LOAD ASSETS ============
const logoBase64 = imageToBase64("./assets/wordmark-dark.png");
const booksIconBase64 = imageToBase64("./assets/books-icon-dark.png");
const booksIconWhiteBase64 = imageToBase64("./assets/books-icon-white.png");
const gradientStripeBase64 = imageToBase64("./assets/gradient-stripe.png");

// ============ SLIDES ============
// ... slide creation code ...

// ============ SAVE ============
pres.writeFile({ fileName: "output.pptx" });
```

### Dependencies

```json
{
  "dependencies": {
    "pptxgenjs": "^3.12.0"
  }
}
```

### Installation

```bash
npm install -g pptxgenjs
# or
npm install pptxgenjs
```

---

## Checklist for New Presentations

- [ ] Set `pres.layout = "LAYOUT_16x9"`
- [ ] Load all logo/icon assets as base64 (wordmark, books icon dark/white, **building icon dark/white**)
- [ ] Use Cardo (or LL Kleisch if embedded) for headlines, Roboto (or KMR Waldenburg if embedded) for body text, Chivo Mono for stat values/data labels
- [ ] Use single text blocks with `indentLevel` for bullet lists
- [ ] Maintain logo aspect ratios (wordmark 5.96:1, books icon 1.26:1, **building icon 0.71:1**)
- [ ] Use v2.0 color names: `plum`, `mint`, `cinder`, `indigo`, `cobalt` (not old palePlum/minty/ember/sky)
- [ ] Use `graphite40` for secondary/supporting text labels
- [ ] Use `indigo` for accent lines, highlights, and people/org slide titles
- [ ] Apply color stripe to title and section slides
- [ ] Apply gradient stripe + white icon to card-based slides
- [ ] Choose books icon (data/content slides) vs building icon (people/org slides)
- [ ] Scale font sizes appropriately for column widths
- [ ] Test output in both PowerPoint and Google Slides

---

## Troubleshooting

### Text Overlapping

**Cause:** Using separate text boxes for each bullet item.  
**Solution:** Use single text block with array of text objects and `indentLevel`.

### Logo Appears Stretched

**Cause:** Width/height ratio doesn't match image aspect ratio.  
**Solution:** Calculate correct dimensions: `h = w / aspectRatio`

### Gradient Has Visible Bands

**Cause:** Using pptxgenjs programmatic gradient with discrete steps.  
**Solution:** Use pre-generated gradient image instead.

### Fonts Don't Display Correctly

**Cause:** Cardo/Roboto fonts not installed on viewing system.  
**Solution:** Fonts are embedded in PPTX; ensure using standard font names.

### Bullets Not Showing

**Cause:** Incorrect bullet code format.  
**Solution:** Use `bullet: { code: "25CF" }` (Unicode without U+ prefix).

---

*Document Version: 2.0*
*Last Updated: March 2026*

# Backstory Presentation Skill (BackstorySlides)

> Reference for creating Backstory branded presentations with calibrated positioning and brand compliance.

**Status:** 🚧 DRAFT - Awaiting boundary calibration

---

## Table of Contents

1. [Overview](#overview)
2. [Brand Colors](#brand-colors)
3. [Asset Inventory](#asset-inventory)
4. [Background Templates](#background-templates) *(To be defined)*
5. [Calibrated Text Boundaries](#calibrated-text-boundaries) *(To be calibrated)*
6. [Typography System](#typography-system) *(To be defined)*
7. [CSS Reference](#css-reference)
8. [HTML Templates](#html-templates)

---

## Overview

This skill creates professional presentations using **Backstory brand guidelines**. Unlike People.ai which uses image-based backgrounds, Backstory uses **solid colors and gradients** from its brand palette.

**Output Formats:**
- HTML (reveal.js) - Interactive web presentations  
- PPTX - Editable in Google Slides, PowerPoint, Keynote

**Key Features:**
- Fixed 16:9 aspect ratio (1920×1080)
- Solid color or gradient backgrounds
- Calibrated text zones *(pending)*
- Logo/icon watermark positioning

---

## Brand Colors

### Primary Palette (from brand guide)

| Name | HEX | RGB | CSS Variable | Usage |
|------|-----|-----|--------------|-------|
| **Black** | #000000 | 0/0/0 | `--bs-black` | Primary dark, text |
| **Graphite** | #171721 | 23/23/33 | `--bs-graphite` | Dark backgrounds |
| **Surface Gray** | #BBBCBC | 187/188/188 | `--bs-surface-gray` | Neutral backgrounds |
| **Horizon** | #6296AD | 98/150/173 | `--bs-horizon` | Accent, headers |
| **White** | #FFFFFF | 255/255/255 | `--bs-white` | Light backgrounds, text |

### Secondary Palette

| Name | HEX | RGB | CSS Variable | Usage |
|------|-----|-----|--------------|-------|
| **Plum** | #AA8FA0 | 170/143/160 | `--bs-plum` | Accent |
| **Mint** | #D7F9DB | 215/249/219 | `--bs-mint` | Highlights, accents |
| **Ember** | #C15228 | 193/82/40 | `--bs-ember` | Warnings, accents |
| **Navy** | #0F2B46 | 15/43/70 | `--bs-navy` | Dark backgrounds |
| **Sky** | #57B2F9 | 87/178/249 | `--bs-sky` | Accents, links |

### Approved Color Combinations

| Background | Approved Text Colors |
|------------|---------------------|
| White | Black |
| Black | White, Plum, Surface Gray, Mint |
| Graphite | Plum, White |
| Surface Gray | Black |
| Horizon | Navy, White |
| Navy | Horizon, Sky, Ember, White |
| Plum | Black |
| Mint | Black |
| Ember | Black, Navy |
| Sky | Navy |

### Gradient Options (from brand swatches)

| Gradient Name | From | To | Suggested Use |
|--------------|------|-----|---------------|
| Ocean Mint | Navy (#0F2B46) | Mint (#D7F9DB) | Title slides |
| Plum Fade | Plum (#AA8FA0) | Graphite (#171721) | Section dividers |
| Steel | Surface Gray (#BBBCBC) | Horizon (#6296AD) | Content |
| Deep Navy | Navy (#0F2B46) | Graphite (#171721) | Dark sections |
| Sky Fire | Sky (#57B2F9) | Ember (#C15228) | Accent slides |

---

## Asset Inventory

### Logos & Icons

| File | Description | Use On |
|------|-------------|--------|
| `image1.png` | Wordmark "Backstory" (dark) | Light backgrounds |
| `image2.png` | Brand icon - books (dark) | Light backgrounds |
| `image5.png` | Logo (white/light version) | Dark backgrounds |
| `image9.png` | Brand icon - books (white) | Dark backgrounds |

### UI Icons

| File | Description |
|------|-------------|
| `image6.png` | Building icon (dark, large) |
| `image11.png` | Building icon (dark, small) |
| `image18.png` | Building icon (variant) |

### Stock Photography

| File | Description | Suggested Use |
|------|-------------|---------------|
| `image3.png` | Headshot (blonde woman) | Team, contact slides |
| `image4.jpg` | Blue hexagon texture | Possible background |
| `image7.jpg` | Tablet with charts | Feature slides |
| `image10.jpg` | Woman at computer (blue lighting) | Feature slides |
| `image13.jpg` | Two people at trading screens | Feature slides |
| `image20.png` | Meeting presentation (B&W) | Feature slides |

### Charts & Graphics (Examples)

| File | Description |
|------|-------------|
| `image8.png` | Pie chart (Enterprise/Mid-Market/SMB) |
| `image14.png` | Engineering Roadmap (Gantt chart) |
| `image15.png` | Donut charts on dark background |

### Brand Reference (Not for use in slides)

| File | Description |
|------|-------------|
| `image12.png` | Color palette with HEX/RGB values |
| `image16.png` | Color combination guide |
| `image17.png` | Color palette categories |
| `image19.png` | Gradient swatches |

---

## Background Templates

### ⚠️ TO BE DEFINED WITH USER

**Option A: Solid Color Backgrounds**
Generate backgrounds programmatically using brand colors.

**Option B: Gradient Backgrounds**  
Use the gradient combinations from brand swatches.

**Option C: Image Background**
Use `image4.jpg` (hexagon texture) for certain slide types.

### Proposed Slide Types

| Slide Type | Background | Text Color | Logo |
|------------|------------|------------|------|
| Title | Navy or Gradient | White | White icon |
| Section Divider | Graphite | White/Plum | White icon |
| Content | White | Black/Graphite | Dark icon |
| Two-Column | White | Black | Dark icon |
| Three-Column | White | Black | Dark icon |
| Feature | Split (image + color) | Varies | Varies |
| Quote | Horizon or Navy | White | White icon |
| Team/Contact | White or Surface Gray | Black | Dark icon |
| Thank You | Gradient or Graphite | White | White icon |

---

## Calibrated Text Boundaries

### ⚠️ PENDING CALIBRATION

Each slide type needs boundary definitions:
- Position: left%, top%
- Size: width%, height%
- Padding
- Logo position

*(To be completed through visual calibration process)*

---

## Typography System

### ⚠️ TO BE DEFINED

**Questions:**
- What is the primary font family?
- What are the heading sizes?
- What are the body text sizes?

### Proposed Starting Point (based on People.ai learnings)

| Element | Size | Weight |
|---------|------|--------|
| Title (hero) | 5em | 700 |
| Section header | 6em | 700 |
| Slide title | 4em | 700 |
| Subtitle | 2.4em | 400 |
| Body text | 3em | 400 |
| Bullet items | 2.5em | 400 |
| Caption | 1.8em | 400 |

---

## CSS Reference

### CSS Variables

```css
:root {
    /* Primary */
    --bs-black: #000000;
    --bs-graphite: #171721;
    --bs-surface-gray: #BBBCBC;
    --bs-horizon: #6296AD;
    --bs-white: #FFFFFF;
    
    /* Secondary */
    --bs-plum: #AA8FA0;
    --bs-mint: #D7F9DB;
    --bs-ember: #C15228;
    --bs-navy: #0F2B46;
    --bs-sky: #57B2F9;
}
```

### Fixed Aspect Ratio (Required)

```css
html, body {
    height: 100%;
    overflow: hidden;
    background: #000;
}

.reveal .slides {
    text-align: left;
}

.reveal .slides section {
    padding: 0;
    height: 100%;
    width: 100%;
}
```

### Reveal.js Configuration

```javascript
Reveal.initialize({
    width: 1920,
    height: 1080,
    margin: 0,
    minScale: 0.1,
    maxScale: 3.0,
    controls: true,
    progress: true,
    center: false,
    hash: true,
    transition: 'slide',
    backgroundTransition: 'fade'
});
```

---

## HTML Templates

### ⚠️ TO BE CREATED AFTER CALIBRATION

Templates will follow this structure:

```html
<section data-background-color="#0F2B46">
    <div class="slide-title">
        <h1>Presentation Title</h1>
        <div class="subtitle">Subtitle text</div>
    </div>
</section>
```

---

## Next Steps

1. **Define which backgrounds to use** - Solid colors, gradients, or images?
2. **Create background images** (if needed) at 1920×1080
3. **Calibrate text boundaries** for each slide type
4. **Confirm typography** - Font family and sizes
5. **Build test presentation** to validate

---

*Document Version: 0.1 DRAFT*  
*Last Updated: February 2026*

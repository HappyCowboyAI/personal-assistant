# Backstory Presentation Skill

> Create professional Backstory-branded presentations for sales and customer success teams.

**Use Cases:** Account Plan Reviews, QBRs, Pricing Proposals, Executive Briefings, Customer Onboarding

**Output Formats:**
- HTML (reveal.js) → Direct viewing or PDF export
- PPTX → Upload to Google Slides for collaborative editing

---

## Quick Start

1. Choose appropriate slide types for your content
2. Use the HTML templates below with reveal.js
3. Replace placeholder content
4. Export or share

---

## Brand Colors

### Primary Palette

| Name | HEX | CSS Variable | Use For |
|------|-----|--------------|---------|
| **Black** | `#000000` | `--bs-black` | Primary text on light BG |
| **Graphite** | `#171721` | `--bs-graphite` | Dark backgrounds, headers |
| **Surface Gray** | `#BBBCBC` | `--bs-surface-gray` | Card backgrounds, borders |
| **Horizon** | `#6296AD` | `--bs-horizon` | Accent cards, Step 1 |
| **White** | `#FFFFFF` | `--bs-white` | Light backgrounds, text on dark |

### Secondary Palette

| Name | HEX | CSS Variable | Use For |
|------|-----|--------------|---------|
| **Plum** | `#AA8FA0` | `--bs-plum` | Accent cards, Step 2 |
| **Mint** | `#CFFAD8` | `--bs-mint` | Highlights, success indicators |
| **Ember** | `#D04911` | `--bs-ember` | Accent cards, Step 3, warnings |
| **Navy** | `#012C48` | `--bs-navy` | Dark cards, Step 4, footers |
| **Sky** | `#21B5FF` | `--bs-sky` | Links, Step 5, highlights |

### Data Visualization Colors

Use this sequence for charts and graphs:
1. Horizon (`#6296AD`) - 42% segments, primary data
2. Navy (`#012C48`) - 38% segments, secondary data  
3. Ember (`#D04911`) - 28% segments, tertiary data

### Color Combinations (Text on Background)

| Background | Approved Text Colors |
|------------|---------------------|
| White | Black |
| Black/Graphite | White, Plum, Surface Gray, Mint |
| Horizon | White, Navy |
| Navy | White, Horizon, Sky, Ember |
| Plum | White, Black |
| Ember | White, Black, Navy |
| Sky | Navy, White |

---

## Typography

### Font Stack

```css
--bs-font-headline: 'Cardo', Georgia, 'Times New Roman', serif;
--bs-font-body: 'Roboto', 'Helvetica Neue', Arial, sans-serif;
```

**Google Fonts Import:**
```html
<link href="https://fonts.googleapis.com/css2?family=Cardo:wght@400;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
```

### Type Scale

| Element | Font | Size | Weight | Line Height |
|---------|------|------|--------|-------------|
| Hero Title | Cardo | 72px (4.5em) | 700 | 1.1 |
| Slide Title | Cardo | 44px (2.75em) | 700 | 1.2 |
| Section Header | Roboto | 30px (1.875em) | 700 | 1.3 |
| Body L1 | Roboto | 28px (1.75em) | 400 | 1.4 |
| Body L2 | Roboto | 26px (1.625em) | 400 | 1.4 |
| Body L3 | Roboto | 24px (1.5em) | 400 | 1.4 |
| Caption | Roboto | 18px (1.125em) | 400 | 1.5 |

### Bullet Styles

- **Level 1:** Filled circle `●` (U+25CF)
- **Level 2:** En-dash `–` (U+2013), indent 0.9"
- **Level 3:** Small square `■` (U+25AA), indent 1.35"

---

## Slide Layouts

### Layout Index

| # | Layout Name | Best For |
|---|-------------|----------|
| 1 | Title Slide | Opening, major sections |
| 2 | Section Divider | Topic transitions |
| 3 | Agenda | Meeting structure |
| 4 | Speaker/Bio | Team introductions |
| 5 | Title + Body | General content |
| 6 | Two Column | Comparisons, pros/cons |
| 7 | Three Column | Feature lists |
| 8 | 3-Step Process | Simple workflows |
| 9 | 4-Step Process | Methodologies |
| 10 | 5-Step Vertical | Detailed processes |
| 11 | Quarterly Timeline | QBR metrics |
| 12 | Image Left | Feature highlights |
| 13 | Image Right | Case studies |
| 14 | Full Image | Impact statements |
| 15 | Comparison Cards | Segment/pricing comparison |
| 16 | Stats/Metrics | KPIs, dashboards |
| 17 | Pie Chart | Market share, distribution |
| 18 | Thank You | Closing |

---

## CSS Foundation

```css
@import url('https://fonts.googleapis.com/css2?family=Cardo:wght@400;700&family=Roboto:wght@400;500;700&display=swap');

:root {
    /* Primary */
    --bs-black: #000000;
    --bs-graphite: #171721;
    --bs-surface-gray: #BBBCBC;
    --bs-horizon: #6296AD;
    --bs-white: #FFFFFF;
    
    /* Secondary */
    --bs-plum: #AA8FA0;
    --bs-mint: #CFFAD8;
    --bs-ember: #D04911;
    --bs-navy: #012C48;
    --bs-sky: #21B5FF;
    
    /* Typography */
    --bs-font-headline: 'Cardo', Georgia, serif;
    --bs-font-body: 'Roboto', sans-serif;
}

/* Reveal.js Overrides */
html, body {
    height: 100%;
    overflow: hidden;
    background: #000;
}

.reveal {
    font-family: var(--bs-font-body);
    font-size: 16px;
    color: var(--bs-black);
}

.reveal .slides {
    text-align: left;
}

.reveal .slides section {
    padding: 0;
    height: 100%;
    width: 100%;
    box-sizing: border-box;
}

.reveal h1, .reveal h2 {
    font-family: var(--bs-font-headline);
    font-weight: 700;
    text-transform: none;
    letter-spacing: -0.02em;
}

.reveal h1 { font-size: 4.5em; }
.reveal h2 { font-size: 2.75em; margin-bottom: 0.5em; }
.reveal h3 { font-size: 1.875em; font-weight: 700; }

/* Books Icon (Bottom Right) */
.bs-icon-br {
    position: absolute;
    bottom: 40px;
    right: 50px;
    width: 80px;
    height: auto;
}

/* Color Stripe Footer */
.bs-color-stripe {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 50px;
    display: flex;
}

.bs-color-stripe > div {
    flex: 1;
}

/* Rounded Border Frame */
.bs-frame {
    position: absolute;
    top: 20px;
    left: 20px;
    right: 20px;
    bottom: 20px;
    border: 3px solid var(--bs-graphite);
    border-radius: 30px;
    padding: 60px;
    box-sizing: border-box;
}

/* Navy Sidebar with Gradient */
.bs-sidebar-gradient {
    position: absolute;
    top: 0;
    right: 0;
    width: 200px;
    height: 100%;
    background: linear-gradient(to bottom, var(--bs-surface-gray), var(--bs-graphite));
}

.bs-sidebar-gradient .bs-icon {
    position: absolute;
    bottom: 60px;
    right: 60px;
    width: 70px;
}

/* Process/Step Cards */
.bs-card {
    padding: 30px;
    border-radius: 15px;
    color: var(--bs-white);
}

.bs-card.horizon { background: var(--bs-horizon); }
.bs-card.plum { background: var(--bs-plum); }
.bs-card.ember { background: var(--bs-ember); }
.bs-card.navy { background: var(--bs-navy); }
.bs-card.sky { background: var(--bs-sky); }

/* Bullet Lists */
.bs-bullets {
    list-style: none;
    padding: 0;
    margin: 0;
}

.bs-bullets li {
    padding-left: 1.5em;
    margin-bottom: 0.75em;
    position: relative;
    font-size: 1.75em;
    line-height: 1.4;
}

.bs-bullets li::before {
    content: '●';
    position: absolute;
    left: 0;
}

.bs-bullets li.l2 {
    padding-left: 2.5em;
    font-size: 1.625em;
}

.bs-bullets li.l2::before {
    content: '–';
    left: 1em;
}

.bs-bullets li.l3 {
    padding-left: 3.5em;
    font-size: 1.5em;
}

.bs-bullets li.l3::before {
    content: '■';
    left: 2em;
    font-size: 0.6em;
    top: 0.4em;
}
```

---

## HTML Templates

### 1. Title Slide

```html
<section data-background-color="#FFFFFF">
    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: calc(100% - 50px); text-align: center; padding: 60px;">
        <h1 style="color: var(--bs-black); margin-bottom: 20px;">PRESENTATION TITLE</h1>
        <p style="font-size: 2em; font-style: italic; color: var(--bs-graphite); margin-bottom: 40px;">Subtitle or tagline goes here</p>
        <img src="backstory-logo-dark.png" alt="Backstory" style="width: 300px;">
    </div>
    <div class="bs-color-stripe">
        <div style="background: var(--bs-surface-gray);"></div>
        <div style="background: var(--bs-plum);"></div>
        <div style="background: var(--bs-horizon);"></div>
        <div style="background: #E8B4A0;"></div>
        <div style="background: var(--bs-surface-gray);"></div>
    </div>
</section>
```

### 2. Section Divider

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame" style="display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;">
        <h1 style="color: var(--bs-black); font-size: 5em;">Section Title</h1>
        <img src="backstory-logo-dark.png" alt="Backstory" style="width: 280px; margin-top: 80px;">
    </div>
    <div class="bs-color-stripe">
        <div style="background: var(--bs-surface-gray);"></div>
        <div style="background: var(--bs-plum);"></div>
        <div style="background: var(--bs-horizon);"></div>
        <div style="background: #E8B4A0;"></div>
        <div style="background: var(--bs-surface-gray);"></div>
    </div>
</section>
```

### 3. Agenda Slide

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame" style="background: url('meeting-photo.jpg') right center / 50% auto no-repeat; background-blend-mode: lighten; background-color: rgba(255,255,255,0.85);">
        <h2 style="color: var(--bs-black); margin-bottom: 50px;">Agenda</h2>
        <div style="max-width: 55%;">
            <div style="margin-bottom: 35px;">
                <h3 style="color: var(--bs-black); margin-bottom: 8px;">●  Topic One</h3>
                <p style="font-size: 1.5em; color: var(--bs-graphite); padding-left: 1.5em;">Description of topic</p>
            </div>
            <div style="margin-bottom: 35px;">
                <h3 style="color: var(--bs-black); margin-bottom: 8px;">●  Topic Two</h3>
                <p style="font-size: 1.5em; color: var(--bs-graphite); padding-left: 1.5em;">Description of topic</p>
            </div>
            <div style="margin-bottom: 35px;">
                <h3 style="color: var(--bs-black); margin-bottom: 8px;">●  Topic Three</h3>
                <p style="font-size: 1.5em; color: var(--bs-graphite); padding-left: 1.5em;">Description of topic</p>
            </div>
            <div>
                <h3 style="color: var(--bs-black); margin-bottom: 8px;">●  Topic Four</h3>
                <p style="font-size: 1.5em; color: var(--bs-graphite); padding-left: 1.5em;">Description of topic</p>
            </div>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 4. Speaker/Bio Slide

```html
<section data-background-color="#BBBCBC">
    <div class="bs-frame" style="background: var(--bs-white); display: flex;">
        <!-- Left Column -->
        <div style="width: 45%; padding-right: 40px; border-right: 2px solid var(--bs-surface-gray);">
            <img src="headshot.jpg" style="width: 280px; height: 350px; object-fit: cover; margin-bottom: 30px;">
            <h2 style="color: var(--bs-black); font-size: 2.2em; margin-bottom: 10px;">Person Name</h2>
            <p style="font-size: 1.5em; color: var(--bs-graphite);">Title / Role</p>
            <img src="backstory-logo-dark.png" style="width: 200px; margin-top: 40px;">
        </div>
        <!-- Right Column -->
        <div style="width: 55%; padding-left: 40px; display: flex; flex-direction: column; justify-content: center;">
            <p style="font-size: 1.5em; line-height: 1.6; color: var(--bs-black); margin-bottom: 25px;">
                First paragraph of bio text. Describe background, expertise, and current role.
            </p>
            <p style="font-size: 1.5em; line-height: 1.6; color: var(--bs-black); margin-bottom: 25px;">
                Second paragraph with additional details about experience and achievements.
            </p>
            <p style="font-size: 1.5em; line-height: 1.6; color: var(--bs-black);">
                Third paragraph with notable companies or credentials.
            </p>
        </div>
    </div>
</section>
```

### 5. Title + Body (Bullets)

```html
<section data-background-color="#FFFFFF">
    <div style="padding: 60px 80px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">Slide Title Here</h2>
        <ul class="bs-bullets">
            <li>First level bullet point with key information</li>
            <li>Another main point to discuss
                <ul class="bs-bullets" style="margin-top: 15px;">
                    <li class="l2">Second level supporting detail</li>
                    <li class="l2">Additional context or example</li>
                </ul>
            </li>
            <li>Third main point
                <ul class="bs-bullets" style="margin-top: 15px;">
                    <li class="l2">Supporting information
                        <ul class="bs-bullets" style="margin-top: 10px;">
                            <li class="l3">Third level detail</li>
                        </ul>
                    </li>
                </ul>
            </li>
        </ul>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 6. Two Column Layout

```html
<section data-background-color="#FFFFFF">
    <div style="padding: 60px 80px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">Two Column Title</h2>
        <div style="display: flex; gap: 60px;">
            <!-- Left Column -->
            <div style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px;">Column One Header</h3>
                <ul class="bs-bullets">
                    <li>First point in left column</li>
                    <li>Second point with details
                        <ul class="bs-bullets" style="margin-top: 10px;">
                            <li class="l2">Supporting detail</li>
                        </ul>
                    </li>
                    <li>Third point</li>
                </ul>
            </div>
            <!-- Right Column -->
            <div style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px;">Column Two Header</h3>
                <ul class="bs-bullets">
                    <li>First point in right column</li>
                    <li>Second point with context
                        <ul class="bs-bullets" style="margin-top: 10px;">
                            <li class="l2">Additional information</li>
                        </ul>
                    </li>
                    <li>Third point</li>
                </ul>
            </div>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 7. Three Column Layout

```html
<section data-background-color="#FFFFFF">
    <div style="padding: 60px 80px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">Three Column Title</h2>
        <div style="display: flex; gap: 40px;">
            <div style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px; font-size: 1.5em;">Column One</h3>
                <p style="font-size: 1.4em; line-height: 1.5; color: var(--bs-graphite);">
                    Content for the first column. Keep text concise for three-column layouts.
                </p>
            </div>
            <div style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px; font-size: 1.5em;">Column Two</h3>
                <p style="font-size: 1.4em; line-height: 1.5; color: var(--bs-graphite);">
                    Content for the second column. Balance content across all three columns.
                </p>
            </div>
            <div style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px; font-size: 1.5em;">Column Three</h3>
                <p style="font-size: 1.4em; line-height: 1.5; color: var(--bs-graphite);">
                    Content for the third column. Use short paragraphs or bullet points.
                </p>
            </div>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 8. 3-Step Process (Horizontal Cards)

```html
<section data-background-color="#FFFFFF">
    <div class="bs-sidebar-gradient">
        <img src="backstory-icon-white.png" class="bs-icon" alt="">
    </div>
    <div style="padding: 60px 80px; padding-right: 280px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">3-Step Process Title</h2>
        <div style="display: flex; gap: 25px;">
            <!-- Step 1 -->
            <div class="bs-card horizon" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px;">Step 1 Heading</h3>
                <ul style="list-style: disc; padding-left: 1.5em; font-size: 1.3em; line-height: 1.5;">
                    <li>First action item</li>
                    <li>Second action item</li>
                    <li>Third action item</li>
                </ul>
            </div>
            <!-- Step 2 -->
            <div class="bs-card plum" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px;">Step 2 Heading</h3>
                <ul style="list-style: disc; padding-left: 1.5em; font-size: 1.3em; line-height: 1.5;">
                    <li>First action item</li>
                    <li>Second action item</li>
                    <li>Third action item</li>
                </ul>
            </div>
            <!-- Step 3 -->
            <div class="bs-card ember" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 20px;">Step 3 Heading</h3>
                <ul style="list-style: disc; padding-left: 1.5em; font-size: 1.3em; line-height: 1.5;">
                    <li>First action item</li>
                    <li>Second action item</li>
                    <li>Third action item</li>
                </ul>
            </div>
        </div>
    </div>
</section>
```

### 9. 4-Step Process (Horizontal Cards)

```html
<section data-background-color="#FFFFFF">
    <div class="bs-sidebar-gradient">
        <img src="backstory-icon-white.png" class="bs-icon" alt="">
    </div>
    <div style="padding: 60px 80px; padding-right: 280px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">4-Step Process Title</h2>
        <div style="display: flex; gap: 20px;">
            <div class="bs-card horizon" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px; font-size: 1.3em;">Step 1</h3>
                <p style="font-size: 1.1em; line-height: 1.4;">Description of first step</p>
            </div>
            <div class="bs-card plum" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px; font-size: 1.3em;">Step 2</h3>
                <p style="font-size: 1.1em; line-height: 1.4;">Description of second step</p>
            </div>
            <div class="bs-card ember" style="flex: 1;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px; font-size: 1.3em;">Step 3</h3>
                <p style="font-size: 1.1em; line-height: 1.4;">Description of third step</p>
            </div>
            <div class="bs-card navy" style="flex: 1;">
                <h3 style="color: var(--bs-white); margin-bottom: 15px; font-size: 1.3em;">Step 4</h3>
                <p style="font-size: 1.1em; line-height: 1.4;">Description of fourth step</p>
            </div>
        </div>
    </div>
</section>
```

### 10. 5-Step Vertical Process

```html
<section data-background-color="#FFFFFF">
    <div class="bs-sidebar-gradient">
        <img src="backstory-icon-white.png" class="bs-icon" alt="">
    </div>
    <div style="padding: 60px 80px; padding-right: 280px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 30px;">5-Step Vertical Process</h2>
        <div style="display: flex; flex-direction: column; gap: 15px;">
            <div class="bs-card horizon" style="padding: 20px 30px; display: flex; align-items: center;">
                <strong style="margin-right: 20px; font-size: 1.3em;">Process 1:</strong>
                <span style="font-size: 1.2em; font-style: italic;">Description of this step</span>
            </div>
            <div class="bs-card plum" style="padding: 20px 30px; display: flex; align-items: center;">
                <strong style="margin-right: 20px; font-size: 1.3em;">Process 2:</strong>
                <span style="font-size: 1.2em; font-style: italic;">Description of this step</span>
            </div>
            <div class="bs-card ember" style="padding: 20px 30px; display: flex; align-items: center;">
                <strong style="margin-right: 20px; font-size: 1.3em;">Process 3:</strong>
                <span style="font-size: 1.2em; font-style: italic;">Description of this step</span>
            </div>
            <div class="bs-card navy" style="padding: 20px 30px; display: flex; align-items: center;">
                <strong style="margin-right: 20px; font-size: 1.3em;">Process 4:</strong>
                <span style="font-size: 1.2em; font-style: italic;">Description of this step</span>
            </div>
            <div class="bs-card sky" style="padding: 20px 30px; display: flex; align-items: center;">
                <strong style="color: var(--bs-navy); margin-right: 20px; font-size: 1.3em;">Process 5:</strong>
                <span style="color: var(--bs-navy); font-size: 1.2em; font-style: italic;">Description of this step</span>
            </div>
        </div>
    </div>
</section>
```

### 11. Quarterly Timeline (QBR)

```html
<section data-background-color="#FFFFFF">
    <div class="bs-sidebar-gradient">
        <img src="backstory-icon-white.png" class="bs-icon" alt="">
    </div>
    <div style="padding: 60px 80px; padding-right: 280px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 30px;">Quarterly Timeline</h2>
        <div style="display: flex; gap: 20px;">
            <!-- Q1 -->
            <div style="flex: 1; text-align: center;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px;">Q1</h3>
                <div class="bs-card horizon" style="padding: 25px 20px; border-radius: 20px; min-height: 300px;">
                    <p style="font-size: 1.2em; margin-bottom: 20px;">Metric Label</p>
                    <p style="font-size: 3em; font-weight: 700; margin-bottom: 10px;">$XXX</p>
                    <p style="font-size: 2.5em; font-weight: 700; margin-bottom: 15px;">XX%</p>
                    <p style="font-size: 1em;">Context for the metrics</p>
                </div>
            </div>
            <!-- Q2 -->
            <div style="flex: 1; text-align: center;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px;">Q2</h3>
                <div class="bs-card plum" style="padding: 25px 20px; border-radius: 20px; min-height: 300px;">
                    <p style="font-size: 1.2em; margin-bottom: 20px;">Metric Label</p>
                    <p style="font-size: 3em; font-weight: 700; margin-bottom: 10px;">$XXX</p>
                    <p style="font-size: 2.5em; font-weight: 700; margin-bottom: 15px;">XX%</p>
                    <p style="font-size: 1em;">Context for the metrics</p>
                </div>
            </div>
            <!-- Q3 -->
            <div style="flex: 1; text-align: center;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px;">Q3</h3>
                <div class="bs-card ember" style="padding: 25px 20px; border-radius: 20px; min-height: 300px;">
                    <p style="font-size: 1.2em; margin-bottom: 20px;">Metric Label</p>
                    <p style="font-size: 3em; font-weight: 700; margin-bottom: 10px;">$XXX</p>
                    <p style="font-size: 2.5em; font-weight: 700; margin-bottom: 15px;">XX%</p>
                    <p style="font-size: 1em;">Context for the metrics</p>
                </div>
            </div>
            <!-- Q4 -->
            <div style="flex: 1; text-align: center;">
                <h3 style="color: var(--bs-black); margin-bottom: 15px;">Q4</h3>
                <div class="bs-card navy" style="padding: 25px 20px; border-radius: 20px; min-height: 300px;">
                    <p style="font-size: 1.2em; margin-bottom: 20px;">Metric Label</p>
                    <p style="font-size: 3em; font-weight: 700; margin-bottom: 10px;">$XXX</p>
                    <p style="font-size: 2.5em; font-weight: 700; margin-bottom: 15px;">XX%</p>
                    <p style="font-size: 1em;">Context for the metrics</p>
                </div>
            </div>
        </div>
    </div>
</section>
```

### 12. Image Left + Text Right

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame" style="display: flex; padding: 0; overflow: hidden;">
        <div style="width: 50%; background: url('feature-image.jpg') center / cover;"></div>
        <div style="width: 50%; padding: 60px; display: flex; flex-direction: column; justify-content: center;">
            <h2 style="color: var(--bs-black); margin-bottom: 30px;">Feature Title</h2>
            <p style="font-size: 1.5em; line-height: 1.6; color: var(--bs-graphite);">
                Description of the feature or benefit. Explain the value proposition clearly.
            </p>
            <img src="backstory-logo-dark.png" style="width: 180px; margin-top: auto;">
        </div>
    </div>
</section>
```

### 13. Image Right + Text Left

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame" style="display: flex; padding: 0; overflow: hidden;">
        <div style="width: 50%; padding: 60px; display: flex; flex-direction: column; justify-content: center;">
            <h2 style="color: var(--bs-black); margin-bottom: 30px;">Feature Title</h2>
            <p style="font-size: 1.5em; line-height: 1.6; color: var(--bs-graphite);">
                Description of the feature or benefit. Explain the value proposition clearly.
            </p>
            <img src="backstory-logo-dark.png" style="width: 180px; margin-top: auto;">
        </div>
        <div style="width: 50%; background: url('feature-image.jpg') center / cover;"></div>
    </div>
</section>
```

### 14. Full Image with Text Overlay

```html
<section data-background-image="hexagon-texture.jpg" data-background-size="cover">
    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100%; text-align: center; padding: 60px;">
        <h1 style="color: var(--bs-white); font-size: 4em; text-shadow: 0 2px 20px rgba(0,0,0,0.3);">
            Impact Statement
        </h1>
        <p style="color: var(--bs-white); font-size: 1.8em; font-style: italic; margin-top: 30px; text-shadow: 0 2px 10px rgba(0,0,0,0.3);">
            Supporting text or call to action
        </p>
    </div>
</section>
```

### 15. Comparison Cards (Pricing/Segments)

```html
<section data-background-color="#FFFFFF">
    <div style="padding: 60px 80px; height: 100%; box-sizing: border-box;">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">Comparison Title</h2>
        <div style="display: flex; gap: 30px;">
            <!-- Card 1 -->
            <div style="flex: 1; border: 2px solid var(--bs-surface-gray); border-radius: 10px; overflow: hidden;">
                <div style="padding: 30px;">
                    <div style="font-size: 3em; margin-bottom: 20px;">🏢</div>
                    <h3 style="color: var(--bs-black); margin-bottom: 20px;">Enterprise</h3>
                    <div style="margin-bottom: 15px;">
                        <span style="font-size: 1.2em; color: var(--bs-graphite);">Feature 1</span>
                        <span style="float: right;">●●●●●●●●●●</span>
                    </div>
                    <div style="margin-bottom: 15px;">
                        <span style="font-size: 1.2em; color: var(--bs-graphite);">Feature 2</span>
                        <span style="float: right;">●●</span>
                    </div>
                </div>
                <div style="background: var(--bs-navy); color: var(--bs-white); padding: 25px 30px;">
                    <p style="font-size: 1.3em; margin-bottom: 10px;"><strong>$XXX</strong> Annual</p>
                    <p style="font-size: 1.1em;">Key channels: Description</p>
                </div>
            </div>
            <!-- Card 2 -->
            <div style="flex: 1; border: 2px solid var(--bs-surface-gray); border-radius: 10px; overflow: hidden;">
                <div style="padding: 30px;">
                    <div style="font-size: 3em; margin-bottom: 20px;">🏬</div>
                    <h3 style="color: var(--bs-black); margin-bottom: 20px;">Mid-Market</h3>
                    <div style="margin-bottom: 15px;">
                        <span style="font-size: 1.2em; color: var(--bs-graphite);">Feature 1</span>
                        <span style="float: right;">●●●●●●</span>
                    </div>
                    <div style="margin-bottom: 15px;">
                        <span style="font-size: 1.2em; color: var(--bs-graphite);">Feature 2</span>
                        <span style="float: right;">●</span>
                    </div>
                </div>
                <div style="background: var(--bs-navy); color: var(--bs-white); padding: 25px 30px;">
                    <p style="font-size: 1.3em; margin-bottom: 10px;"><strong>$XX</strong> Annual</p>
                    <p style="font-size: 1.1em;">Key channels: Description</p>
                </div>
            </div>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 16. Stats Dashboard (3 Metrics)

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame">
        <h2 style="color: var(--bs-black); margin-bottom: 50px;">Key Metrics</h2>
        <div style="display: flex; gap: 60px; justify-content: center; align-items: center; height: 60%;">
            <!-- Metric 1 -->
            <div style="text-align: center;">
                <div style="width: 200px; height: 200px; border-radius: 50%; background: conic-gradient(var(--bs-horizon) 0% 42%, var(--bs-surface-gray) 42% 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="width: 140px; height: 140px; border-radius: 50%; background: var(--bs-white); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <span style="font-size: 2.5em; font-weight: 700; color: var(--bs-black);">42%</span>
                    </div>
                </div>
                <p style="margin-top: 20px; font-size: 1.3em; color: var(--bs-graphite);">Enterprise</p>
            </div>
            <!-- Metric 2 -->
            <div style="text-align: center;">
                <div style="width: 200px; height: 200px; border-radius: 50%; background: conic-gradient(var(--bs-navy) 0% 38%, var(--bs-surface-gray) 38% 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="width: 140px; height: 140px; border-radius: 50%; background: var(--bs-white); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <span style="font-size: 2.5em; font-weight: 700; color: var(--bs-black);">38%</span>
                    </div>
                </div>
                <p style="margin-top: 20px; font-size: 1.3em; color: var(--bs-graphite);">Mid-Market</p>
            </div>
            <!-- Metric 3 -->
            <div style="text-align: center;">
                <div style="width: 200px; height: 200px; border-radius: 50%; background: conic-gradient(var(--bs-ember) 0% 28%, var(--bs-surface-gray) 28% 100%); display: flex; align-items: center; justify-content: center;">
                    <div style="width: 140px; height: 140px; border-radius: 50%; background: var(--bs-white); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                        <span style="font-size: 2.5em; font-weight: 700; color: var(--bs-black);">28%</span>
                    </div>
                </div>
                <p style="margin-top: 20px; font-size: 1.3em; color: var(--bs-graphite);">SMB</p>
            </div>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 17. Pie Chart

```html
<section data-background-color="#FFFFFF">
    <div class="bs-frame">
        <h2 style="color: var(--bs-black); margin-bottom: 40px;">Win Rate by Segment</h2>
        <div style="display: flex; justify-content: center; align-items: center; height: 70%;">
            <div style="position: relative; width: 400px; height: 400px;">
                <!-- SVG Pie Chart -->
                <svg viewBox="0 0 100 100" style="width: 100%; height: 100%; transform: rotate(-90deg);">
                    <circle cx="50" cy="50" r="40" fill="transparent" stroke="#6296AD" stroke-width="20" stroke-dasharray="105.6 264" stroke-dashoffset="0"/>
                    <circle cx="50" cy="50" r="40" fill="transparent" stroke="#012C48" stroke-width="20" stroke-dasharray="95.4 264" stroke-dashoffset="-105.6"/>
                    <circle cx="50" cy="50" r="40" fill="transparent" stroke="#D04911" stroke-width="20" stroke-dasharray="70.3 264" stroke-dashoffset="-201"/>
                </svg>
                <!-- Labels would be positioned absolutely -->
            </div>
        </div>
        <div style="display: flex; justify-content: center; gap: 40px; margin-top: 20px;">
            <span style="font-size: 1.2em;"><span style="color: var(--bs-horizon);">●</span> Enterprise 42%</span>
            <span style="font-size: 1.2em;"><span style="color: var(--bs-navy);">●</span> Mid-Market 38%</span>
            <span style="font-size: 1.2em;"><span style="color: var(--bs-ember);">●</span> SMB 28%</span>
        </div>
        <img src="backstory-icon-dark.png" class="bs-icon-br" alt="">
    </div>
</section>
```

### 18. Thank You Slide

```html
<section data-background-color="#FFFFFF">
    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: calc(100% - 50px); text-align: center; padding: 60px;">
        <h1 style="color: var(--bs-black); font-size: 5em;">THANK YOU</h1>
        <img src="backstory-logo-dark.png" alt="Backstory" style="width: 300px; margin-top: 60px;">
    </div>
    <div class="bs-color-stripe">
        <div style="background: var(--bs-surface-gray);"></div>
        <div style="background: var(--bs-plum);"></div>
        <div style="background: var(--bs-horizon);"></div>
        <div style="background: #E8B4A0;"></div>
        <div style="background: var(--bs-surface-gray);"></div>
    </div>
</section>
```

---

## Complete HTML Boilerplate

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Presentation Title | Backstory</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.6.1/reveal.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.6.1/theme/white.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Cardo:wght@400;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        /* Paste CSS Foundation here */
    </style>
</head>
<body>
    <div class="reveal">
        <div class="slides">
            <!-- Paste slide sections here -->
        </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.6.1/reveal.min.js"></script>
    <script>
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
    </script>
</body>
</html>
```

---

## Asset Requirements

| Asset | Filename | Used In |
|-------|----------|---------|
| Logo (dark) | `backstory-logo-dark.png` | Title, Section, Bio, Thank You |
| Logo (white) | `backstory-logo-white.png` | Dark backgrounds |
| Icon (dark) | `backstory-icon-dark.png` | Content slides (BR corner) |
| Icon (white) | `backstory-icon-white.png` | Gradient sidebar |
| Hexagon texture | `hexagon-texture.jpg` | Full image overlay |

---

## Presentation Type Guidelines

### Account Plan Review
Recommended slides: Title → Agenda → Speaker → 2-Column (Objectives) → Stats → Quarterly Timeline → 3-Step Process (Next Steps) → Thank You

### QBR (Quarterly Business Review)
Recommended slides: Title → Agenda → Stats Dashboard → Quarterly Timeline → Pie Chart → Comparison Cards → 3-Step Process (Action Items) → Thank You

### Pricing Proposal
Recommended slides: Title → Agenda → Full Image (Value Prop) → 2-Column (Features) → Comparison Cards (Tiers) → Stats (ROI) → Thank You

### Executive Briefing
Recommended slides: Title → Agenda → Image Left (Company Overview) → 3-Column (Key Points) → Stats → 4-Step Process (Roadmap) → Thank You

---

## Export to Google Slides

### Method 1: PDF Import
1. Open presentation in browser
2. Press `?` then `Print` or use browser print
3. Save as PDF
4. Upload PDF to Google Drive
5. Open with Google Slides

### Method 2: PPTX Conversion
1. Use LibreOffice to convert HTML to PPTX
2. Upload PPTX to Google Drive
3. Open with Google Slides

---

*Document Version: 1.0*  
*Last Updated: February 2026*

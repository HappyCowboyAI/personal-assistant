const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// Backstory Brand Colors (no # prefix for pptxgenjs)
const COLORS = {
    black: "000000",
    graphite: "171721",
    surfaceGray: "BBBCBC",
    horizon: "6296AD",
    white: "FFFFFF",
    plum: "AA8FA0",
    mint: "CFFAD8",
    ember: "D04911",
    navy: "012C48",
    sky: "21B5FF",
    salmon: "E8A090"
};

// Style Guide Text Specifications
const TEXT_STYLES = {
    // Body text tiers (for bulleted lists)
    tier1: {
        fontSize: 36,
        fontFace: "Roboto",
        bullet: { code: "25CF" }, // ● small round bullet
        paraSpaceBefore: 24,     // 24pt above
        paraSpaceAfter: 12,      // 12pt below
        indentLevel: 0
    },
    tier2: {
        fontSize: 34,
        fontFace: "Roboto",
        bullet: { code: "2013" }, // – N dash
        paraSpaceBefore: 8,
        paraSpaceAfter: 8,
        indentLevel: 0.9         // 0.9" indent
    },
    tier3: {
        fontSize: 32,
        fontFace: "Roboto",
        bullet: { code: "25AA" }, // ▪ small square
        paraSpaceBefore: 8,
        paraSpaceAfter: 8,
        indentLevel: 1.35        // 1.35" indent
    },
    // Column layout subtitles
    col2Subtitle: { fontSize: 30, fontFace: "Roboto" },
    col3Subtitle: { fontSize: 28, fontFace: "Roboto" },
    col4Subtitle: { fontSize: 22, fontFace: "Roboto" },
    // Headlines use Cardo
    headline: { fontFace: "Cardo", bold: true }
};

// Create presentation
let pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Backstory";
pres.title = "Acme Corp Q4 2025 QBR";
pres.subject = "Quarterly Business Review";

// Helper: Convert image to base64
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

// Load images (transparent logos extracted from original PPTX)
const logoBase64 = imageToBase64("/home/claude/transparent-logos/wordmark-dark.png");
const booksIconBase64 = imageToBase64("/home/claude/transparent-logos/books-icon-dark.png");
const booksIconWhiteBase64 = imageToBase64("/home/claude/transparent-logos/books-icon-white.png");

// Helper: Calculate font size to fit text in given width
// Returns fontSize that will fit the text within the specified width (in inches)
function calcFontSize(text, maxWidth, maxFontSize, minFontSize = 12) {
    // Conservative estimate: average char width ≈ 0.7 of font size in points
    // Georgia/serif fonts tend to be wider than sans-serif
    // 1 inch = 72 points, so width_in_inches = chars * fontSize * charWidthRatio / 72
    const charWidthRatio = 0.7;
    
    // Calculate max font size that fits
    const fittedSize = (maxWidth * 72) / (text.length * charWidthRatio);
    
    // Clamp between min and max
    return Math.max(minFontSize, Math.min(maxFontSize, Math.floor(fittedSize)));
}

// Helper: Add color stripe at bottom
function addColorStripe(slide, y = 5.1) {
    const stripeColors = [COLORS.surfaceGray, COLORS.plum, COLORS.horizon, COLORS.salmon, COLORS.surfaceGray];
    stripeColors.forEach((color, i) => {
        slide.addShape("rect", {
            x: i * 2, y: y, w: 2, h: 0.525,
            fill: { color: color },
            line: { color: color, width: 0 }
        });
    });
}

// Helper: Add books icon (now using transparent PNG from PPTX)
function addBooksIcon(slide, x = 8.85, y = 4.65, w = 0.7, h = 0.55) {
    if (booksIconBase64) {
        slide.addImage({ data: booksIconBase64, x, y, w, h });
    }
}

// Helper: Add logo (transparent wordmark from PPTX)
function addLogo(slide, x = 3.5, y = 3.4, w = 3.0, h = 0.5) {
    if (logoBase64) {
        slide.addImage({ data: logoBase64, x, y, w, h });
    }
}

// Load gradient stripe image
const gradientStripeBase64 = imageToBase64("/home/claude/transparent-logos/gradient-stripe.png");

// Helper: Add navy gradient stripe on right (using smooth gradient image)
function addNavyStripe(slide) {
    // Add the gradient stripe image
    if (gradientStripeBase64) {
        slide.addImage({ 
            data: gradientStripeBase64, 
            x: 8.2, y: 0, w: 1.8, h: 5.625 
        });
    }
    
    // Add white books icon - aspect ratio 1.26:1 (628x498)
    if (booksIconWhiteBase64) {
        slide.addImage({ data: booksIconWhiteBase64, x: 8.55, y: 4.55, w: 0.7, h: 0.55 });
    }
}

// Helper: Add rounded border frame
function addFrame(slide) {
    slide.addShape("roundRect", {
        x: 0.2, y: 0.2, w: 9.6, h: 5.2,
        fill: { type: "none" },
        line: { color: COLORS.graphite, width: 2 },
        rectRadius: 0.3
    });
}

// ============ SLIDE 1: Title ============
let slide1 = pres.addSlide();
slide1.background = { color: COLORS.white };

const slide1Title = "Acme Corp";
const slide1Subtitle = "Q4 2025 Quarterly Business Review";

slide1.addText(slide1Title, {
    x: 0.5, y: 1.4, w: 9, h: 1.2,
    fontSize: calcFontSize(slide1Title, 9, 72, 48), fontFace: "Cardo", bold: true,
    color: COLORS.black, align: "center"
});

slide1.addText(slide1Subtitle, {
    x: 0.5, y: 2.6, w: 9, h: 0.6,
    fontSize: calcFontSize(slide1Subtitle, 9, 28, 18), fontFace: "Cardo", italic: true,
    color: COLORS.graphite, align: "center"
});

addLogo(slide1, 3.5, 3.4, 3.0, 0.5);
addColorStripe(slide1);

// ============ SLIDE 2: Agenda ============
let slide2 = pres.addSlide();
slide2.background = { color: COLORS.white };
addFrame(slide2);

const slide2Title = "Agenda";
slide2.addText(slide2Title, {
    x: 0.5, y: 0.5, w: 8, h: 0.8,
    fontSize: calcFontSize(slide2Title, 8, 44, 32), fontFace: "Cardo", bold: true, color: COLORS.black
});

const agendaItems = [
    { topic: "Q4 Performance Highlights", detail: "Key metrics and achievements" },
    { topic: "Wins & Challenges", detail: "What worked and lessons learned" },
    { topic: "Product Adoption", detail: "Usage trends and engagement metrics" },
    { topic: "Q1 2026 Priorities", detail: "Roadmap and next steps" }
];

let agendaY = 1.5;
const agendaWidth = 8;
agendaItems.forEach(item => {
    // First tier: bullet ● - scaled for slide fit
    slide2.addText(item.topic, {
        x: 0.6, y: agendaY, w: agendaWidth, h: 0.5,
        fontSize: 24, 
        fontFace: "Roboto", 
        bold: true, 
        color: COLORS.black,
        bullet: TEXT_STYLES.tier1.bullet
    });
    // Second tier: bullet – indented
    slide2.addText(item.detail, {
        x: 0.6 + TEXT_STYLES.tier2.indentLevel, y: agendaY + 0.45, w: agendaWidth - TEXT_STYLES.tier2.indentLevel, h: 0.4,
        fontSize: 20, 
        fontFace: "Roboto", 
        color: COLORS.graphite,
        bullet: TEXT_STYLES.tier2.bullet
    });
    agendaY += 0.95;
});

addBooksIcon(slide2, 8.8, 4.6);

// ============ SLIDE 3: Section - Q4 Performance ============
let slide3 = pres.addSlide();
slide3.background = { color: COLORS.white };

const slide3Title = "Q4 Performance";
slide3.addText(slide3Title, {
    x: 0.5, y: 2.0, w: 9, h: 1.2,
    fontSize: calcFontSize(slide3Title, 9, 64, 40), fontFace: "Cardo", bold: true,
    color: COLORS.black, align: "center"
});

addLogo(slide3, 3.5, 3.8, 3.0, 0.5);
addColorStripe(slide3);

// ============ SLIDE 4: Stats Dashboard ============
let slide4 = pres.addSlide();
slide4.background = { color: COLORS.white };
addFrame(slide4);

const slide4Title = "Key Metrics";
slide4.addText(slide4Title, {
    x: 0.5, y: 0.5, w: 8, h: 0.8,
    fontSize: calcFontSize(slide4Title, 8, 44, 32), fontFace: "Cardo", bold: true, color: COLORS.black
});

const stats = [
    { value: "$2.4M", label: "Revenue Impact", change: "↑ 15% vs Q3" },
    { value: "72", label: "NPS Score", change: "↑ 8 points" },
    { value: "94%", label: "Retention Rate", change: "↑ 2%" }
];

const statPositions = [1.2, 4.2, 7.2];
stats.forEach((stat, i) => {
    const statWidth = 2.5;
    const valueFontSize = calcFontSize(stat.value, statWidth, 60, 36);
    const labelFontSize = calcFontSize(stat.label, statWidth, 20, 14);
    
    slide4.addText(stat.value, {
        x: statPositions[i], y: 1.8, w: statWidth, h: 1.0,
        fontSize: valueFontSize, fontFace: "Cardo", bold: true,
        color: COLORS.navy, align: "center"
    });
    slide4.addText(stat.label, {
        x: statPositions[i], y: 2.9, w: statWidth, h: 0.4,
        fontSize: labelFontSize, fontFace: "Roboto",
        color: COLORS.graphite, align: "center"
    });
    slide4.addText(stat.change, {
        x: statPositions[i], y: 3.3, w: statWidth, h: 0.4,
        fontSize: 16, fontFace: "Roboto", bold: true,
        color: "2E7D32", align: "center"
    });
});

addBooksIcon(slide4, 8.8, 4.6);

// ============ SLIDE 5: Two Column - Wins & Challenges ============
let slide5 = pres.addSlide();
slide5.background = { color: COLORS.white };

const slide5Title = "Wins & Challenges";
slide5.addText(slide5Title, {
    x: 0.5, y: 0.4, w: 8, h: 0.8,
    fontSize: calcFontSize(slide5Title, 8, 44, 32), fontFace: "Cardo", bold: true, color: COLORS.black
});

// Left column - Wins
const winsHeader = "Key Wins";
const columnWidth = 4.2;
// 2-column subtitle
slide5.addText(winsHeader, {
    x: 0.5, y: 1.3, w: columnWidth, h: 0.5,
    fontSize: 26, fontFace: "Roboto", bold: true, color: COLORS.horizon
});

// Single text block with bullet levels
const winsText = [
    { text: "Expanded to 3 new departments", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Marketing, Finance, Operations", options: { bullet: { code: "2013" }, indentLevel: 1 } },
    { text: "100% uptime for 6 consecutive months", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Executive sponsor alignment complete", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "40% reduction in time-to-insight", options: { bullet: { code: "25CF" }, indentLevel: 0 } }
];

slide5.addText(winsText, {
    x: 0.5, y: 1.85, w: columnWidth, h: 3.5,
    fontSize: 16, fontFace: "Roboto",
    color: COLORS.graphite,
    valign: "top",
    paraSpaceAfter: 6
});

// Right column - Challenges
const challHeader = "Challenges";
// 2-column subtitle
slide5.addText(challHeader, {
    x: 5.2, y: 1.3, w: columnWidth, h: 0.5,
    fontSize: 26, fontFace: "Roboto", bold: true, color: COLORS.ember
});

// Single text block with bullet levels
const challText = [
    { text: "EMEA adoption at 62%", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Target was 80%", options: { bullet: { code: "2013" }, indentLevel: 1 } },
    { text: "Integration delays with legacy CRM", options: { bullet: { code: "25CF" }, indentLevel: 0 } },
    { text: "Training completion at 71%", options: { bullet: { code: "25CF" }, indentLevel: 0 } }
];

slide5.addText(challText, {
    x: 5.2, y: 1.85, w: columnWidth, h: 3.5,
    fontSize: 16, fontFace: "Roboto",
    color: COLORS.graphite,
    valign: "top",
    paraSpaceAfter: 6
});

addBooksIcon(slide5);

// ============ SLIDE 6: Section - Looking Ahead ============
let slide6 = pres.addSlide();
slide6.background = { color: COLORS.white };

const slide6Title = "Looking Ahead";
slide6.addText(slide6Title, {
    x: 0.5, y: 2.0, w: 9, h: 1.2,
    fontSize: calcFontSize(slide6Title, 9, 64, 40), fontFace: "Cardo", bold: true,
    color: COLORS.black, align: "center"
});

addLogo(slide6, 3.5, 3.8, 3.0, 0.5);
addColorStripe(slide6);

// ============ SLIDE 7: Process Cards - Q1 Priorities ============
let slide7 = pres.addSlide();
slide7.background = { color: COLORS.white };
addNavyStripe(slide7);

const slide7Title = "Q1 2026 Priorities";
slide7.addText(slide7Title, {
    x: 0.5, y: 0.4, w: 7, h: 0.8,
    fontSize: calcFontSize(slide7Title, 7, 44, 32), fontFace: "Cardo", bold: true, color: COLORS.black
});

const priorities = [
    { title: "EMEA Training", color: COLORS.horizon, items: ["Launch localized program", "Assign regional champions", "Target: 90% by March"] },
    { title: "Integration", color: COLORS.plum, items: ["Complete CRM sync Feb 15", "Enable bi-directional flow", "Validate data accuracy"] },
    { title: "Certification", color: COLORS.ember, items: ["Enroll 25 power users", "Complete cert track", "Create internal CoE"] }
];

const cardX = [0.5, 3.0, 5.5];
const cardContentWidth = 2.1;
priorities.forEach((priority, i) => {
    // Card background
    slide7.addShape("roundRect", {
        x: cardX[i], y: 1.4, w: 2.4, h: 3.5,
        fill: { color: priority.color },
        line: { color: priority.color, width: 0 },
        rectRadius: 0.15
    });
    
    // Card title - 3 column subtitle: 28pt (scaled for card width)
    slide7.addText(priority.title, {
        x: cardX[i] + 0.15, y: 1.55, w: cardContentWidth, h: 0.5,
        fontSize: Math.min(TEXT_STYLES.col3Subtitle.fontSize, calcFontSize(priority.title, cardContentWidth, TEXT_STYLES.col3Subtitle.fontSize, 14)), 
        fontFace: TEXT_STYLES.col3Subtitle.fontFace, bold: true, color: COLORS.white
    });
    
    // Card items with tier1 bullet style
    let itemY = 2.2;
    priority.items.forEach(item => {
        slide7.addText(item, {
            x: cardX[i] + 0.15, y: itemY, w: cardContentWidth, h: 0.45,
            fontSize: calcFontSize(item, cardContentWidth, 16, 12), fontFace: "Roboto", color: COLORS.white,
            bullet: TEXT_STYLES.tier1.bullet
        });
        itemY += 0.55;
    });
});

// ============ SLIDE 8: Quarterly Timeline ============
let slide8 = pres.addSlide();
slide8.background = { color: COLORS.white };
addNavyStripe(slide8);

const slide8Title = "2026 Roadmap";
slide8.addText(slide8Title, {
    x: 0.5, y: 0.4, w: 7, h: 0.8,
    fontSize: calcFontSize(slide8Title, 7, 44, 32), fontFace: "Cardo", bold: true, color: COLORS.black
});

const quarters = [
    { q: "Q1", focus: "EMEA", sub: "Training", note: "90% completion target", color: COLORS.horizon },
    { q: "Q2", focus: "Scale", sub: "Expansion", note: "2 new business units", color: COLORS.plum },
    { q: "Q3", focus: "Advanced", sub: "Features", note: "AI insights rollout", color: COLORS.ember },
    { q: "Q4", focus: "Renew", sub: "& Grow", note: "Multi-year discussion", color: COLORS.navy }
];

const qCardX = [0.5, 2.45, 4.4, 6.35];
const qCardWidth = 1.8;
quarters.forEach((quarter, i) => {
    // Quarter label - 4 column subtitle: 22pt (scaled for card width)
    slide8.addText(quarter.q, {
        x: qCardX[i], y: 1.3, w: qCardWidth, h: 0.4,
        fontSize: Math.min(TEXT_STYLES.col4Subtitle.fontSize, calcFontSize(quarter.q, qCardWidth, TEXT_STYLES.col4Subtitle.fontSize, 14)), 
        fontFace: TEXT_STYLES.col4Subtitle.fontFace, bold: true,
        color: COLORS.black, align: "center"
    });
    
    // Card background
    slide8.addShape("roundRect", {
        x: qCardX[i], y: 1.75, w: qCardWidth, h: 3.0,
        fill: { color: quarter.color },
        line: { color: quarter.color, width: 0 },
        rectRadius: 0.2
    });
    
    // Focus label
    const focusLabel = "Focus Area";
    slide8.addText(focusLabel, {
        x: qCardX[i], y: 1.9, w: qCardWidth, h: 0.35,
        fontSize: calcFontSize(focusLabel, qCardWidth, 12, 9), fontFace: "Roboto", color: COLORS.white, align: "center"
    });
    
    // Focus value - headline style (Cardo)
    slide8.addText(quarter.focus, {
        x: qCardX[i], y: 2.3, w: qCardWidth, h: 0.5,
        fontSize: calcFontSize(quarter.focus, qCardWidth, 28, 18), fontFace: TEXT_STYLES.headline.fontFace, bold: true,
        color: COLORS.white, align: "center"
    });
    
    // Sub value
    slide8.addText(quarter.sub, {
        x: qCardX[i], y: 2.8, w: qCardWidth, h: 0.4,
        fontSize: calcFontSize(quarter.sub, qCardWidth, TEXT_STYLES.col4Subtitle.fontSize, 14), fontFace: "Roboto",
        color: COLORS.white, align: "center"
    });
    
    // Note
    slide8.addText(quarter.note, {
        x: qCardX[i], y: 3.8, w: qCardWidth, h: 0.35,
        fontSize: calcFontSize(quarter.note, qCardWidth, 11, 8), fontFace: "Roboto",
        color: COLORS.white, align: "center"
    });
});

// ============ SLIDE 9: Thank You ============
let slide9 = pres.addSlide();
slide9.background = { color: COLORS.white };

const slide9Title = "THANK YOU";
slide9.addText(slide9Title, {
    x: 0.5, y: 1.8, w: 9, h: 1.5,
    fontSize: calcFontSize(slide9Title, 9, 80, 48), fontFace: "Cardo", bold: true,
    color: COLORS.black, align: "center",
    charSpacing: 8
});

addLogo(slide9, 3.5, 3.5, 3.0, 0.5);
addColorStripe(slide9);

// Save the presentation
pres.writeFile({ fileName: "/mnt/user-data/outputs/AcmeCorp-QBR-Sample.pptx" })
    .then(fileName => {
        console.log(`Created: ${fileName}`);
    })
    .catch(err => {
        console.error(err);
    });

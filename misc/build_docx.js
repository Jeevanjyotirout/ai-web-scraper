const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition, ExternalHyperlink,
} = require("docx");
const fs = require("fs");

// ── Data injected by Python via template literal ──────────────────────────────
const ARTICLES = JSON.parse(process.argv[2]);

// ── Palette ───────────────────────────────────────────────────────────────────
const NAVY      = "1F3864";
const MID_BLUE  = "2E75B6";
const LT_BLUE   = "D6E4F0";
const ORANGE    = "E97132";
const WHITE     = "FFFFFF";
const GREY_BG   = "F5F5F5";
const BORDER_C  = "CCCCCC";

const STATUS_COLOR = { Published: "C6EFCE", Review: "FFEB9C", Draft: "FFCCCC" };

// ── Helpers ────────────────────────────────────────────────────────────────────
const thinBorder = (color = BORDER_C) => ({ style: BorderStyle.SINGLE, size: 1, color });
const cellBorders = (color) => ({ top: thinBorder(color), bottom: thinBorder(color), left: thinBorder(color), right: thinBorder(color) });
const noBorders = () => {
  const nb = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  return { top: nb, bottom: nb, left: nb, right: nb };
};

function hRule(color = MID_BLUE) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color, space: 1 } },
    spacing: { after: 0 },
    children: [],
  });
}

function spacer(pts = 120) {
  return new Paragraph({ spacing: { before: pts, after: 0 }, children: [] });
}

// ── Table of Contents (manual, since auto-TOC needs field update) ─────────────
function buildTOC() {
  const rows = ARTICLES.map((a, i) =>
    new TableRow({
      children: [
        new TableCell({
          borders: noBorders(),
          width: { size: 7200, type: WidthType.DXA },
          margins: { top: 40, bottom: 40, left: 0, right: 80 },
          children: [new Paragraph({
            children: [new TextRun({ text: `${i + 1}.  ${a.title}`, font: "Arial", size: 20 })],
          })],
        }),
        new TableCell({
          borders: noBorders(),
          width: { size: 2160, type: WidthType.DXA },
          margins: { top: 40, bottom: 40, left: 80, right: 0 },
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: a.author, font: "Arial", size: 18, color: "666666", italics: true })],
          })],
        }),
      ],
    })
  );

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [7200, 2160],
    rows,
  });
}

// ── Summary stats table ───────────────────────────────────────────────────────
function buildSummaryTable() {
  const totalReads  = ARTICLES.reduce((s, a) => s + a.reads, 0);
  const totalLikes  = ARTICLES.reduce((s, a) => s + a.likes, 0);
  const avgEngage   = (ARTICLES.reduce((s, a) => s + a.engagement_rate, 0) / ARTICLES.length).toFixed(2);
  const published   = ARTICLES.filter(a => a.status === "Published").length;
  const categories  = [...new Set(ARTICLES.map(a => a.category))].length;

  const stats = [
    ["Total Articles",  ARTICLES.length.toString()],
    ["Total Reads",     totalReads.toLocaleString()],
    ["Total Likes",     totalLikes.toLocaleString()],
    ["Avg Engagement",  `${avgEngage}%`],
    ["Published",       `${published} / ${ARTICLES.length}`],
    ["Categories",      categories.toString()],
  ];

  const rows = [];
  for (let i = 0; i < stats.length; i += 2) {
    const pair = [stats[i], stats[i + 1] || ["", ""]];
    rows.push(new TableRow({
      children: pair.map(([label, value]) => [
        new TableCell({
          borders: cellBorders(BORDER_C),
          width: { size: 2340, type: WidthType.DXA },
          shading: { fill: MID_BLUE, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({
            children: [new TextRun({ text: label, font: "Arial", size: 18, bold: true, color: WHITE })],
          })],
        }),
        new TableCell({
          borders: cellBorders(BORDER_C),
          width: { size: 2340, type: WidthType.DXA },
          shading: { fill: LT_BLUE, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: value, font: "Arial", size: 22, bold: true, color: NAVY })],
          })],
        }),
      ]).flat(),
    }));
  }

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2340, 2340, 2340, 2340],
    rows,
  });
}

// ── Per-article section ───────────────────────────────────────────────────────
function buildArticleSection(article, index) {
  const tagText = article.tags.join("  ·  ");
  const statusColor = STATUS_COLOR[article.status] || "EEEEEE";

  const metaRow = new TableRow({
    children: [
      ["Author",       article.author],
      ["Category",     article.category],
      ["Date",         article.date],
      ["Word Count",   article.word_count.toLocaleString()],
      ["Status",       article.status],
    ].map(([label, val], ci) =>
      new TableCell({
        borders: cellBorders(BORDER_C),
        width: { size: 1872, type: WidthType.DXA },
        shading: {
          fill: ci === 4 ? statusColor : GREY_BG,
          type: ShadingType.CLEAR,
        },
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [
          new Paragraph({ children: [new TextRun({ text: label, font: "Arial", size: 16, bold: true, color: "555555" })] }),
          new Paragraph({ children: [new TextRun({ text: val, font: "Arial", size: 18, bold: ci === 4 })] }),
        ],
      })
    ),
  });

  const metricsRow = new TableRow({
    children: [
      ["Reads",        article.reads.toLocaleString(),  MID_BLUE],
      ["Likes",        article.likes.toLocaleString(),  NAVY],
      ["Engagement",   `${article.engagement_rate}%`,   ORANGE],
    ].map(([label, val, color]) =>
      new TableCell({
        borders: cellBorders(BORDER_C),
        width: { size: 3120, type: WidthType.DXA },
        shading: { fill: LT_BLUE, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: val, font: "Arial", size: 28, bold: true, color })],
          }),
          new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: label, font: "Arial", size: 16, color: "666666" })],
          }),
        ],
      })
    ),
  });

  return [
    spacer(200),

    // Article number + title
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      children: [
        new TextRun({ text: `${index + 1}. `, font: "Arial", size: 32, bold: true }),
        new TextRun({ text: article.title, font: "Arial", size: 32, bold: true }),
      ],
    }),

    hRule(),
    spacer(80),

    // Meta table
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [1872, 1872, 1872, 1872, 1872],
      rows: [metaRow],
    }),

    spacer(100),

    // Summary label
    new Paragraph({
      children: [new TextRun({ text: "SUMMARY", font: "Arial", size: 18, bold: true, color: MID_BLUE })],
    }),
    spacer(40),

    // Summary body
    new Paragraph({
      children: [new TextRun({ text: article.summary, font: "Arial", size: 20 })],
      spacing: { line: 360 },
    }),

    spacer(100),

    // Tags label
    new Paragraph({
      children: [new TextRun({ text: "TAGS", font: "Arial", size: 18, bold: true, color: MID_BLUE })],
    }),
    spacer(40),
    new Paragraph({
      children: article.tags.map((tag, ti) => [
        new TextRun({ text: tag, font: "Arial", size: 18, bold: true }),
        ti < article.tags.length - 1
          ? new TextRun({ text: "   ·   ", font: "Arial", size: 18, color: "AAAAAA" })
          : new TextRun(""),
      ]).flat(),
    }),

    spacer(100),

    // Metrics section
    new Paragraph({
      children: [new TextRun({ text: "PERFORMANCE METRICS", font: "Arial", size: 18, bold: true, color: MID_BLUE })],
    }),
    spacer(40),

    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [3120, 3120, 3120],
      rows: [metricsRow],
    }),

    spacer(60),
  ];
}

// ── Cover page ────────────────────────────────────────────────────────────────
function buildCoverSection() {
  const now = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  return [
    spacer(800),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "ARTICLE DATASET", font: "Arial", size: 56, bold: true, color: NAVY })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "COMPREHENSIVE REPORT", font: "Arial", size: 36, color: MID_BLUE })],
    }),
    spacer(120),
    hRule(MID_BLUE),
    spacer(120),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: `${ARTICLES.length} Articles  ·  Multiple Categories  ·  Full Analytics`, font: "Arial", size: 22, color: "555555", italics: true })],
    }),
    spacer(80),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: `Generated: ${now}`, font: "Arial", size: 20, color: "777777" })],
    }),
    spacer(200),
    new Paragraph({
      children: [new PageBreak()],
    }),
  ];
}

// ── Main document assembly ────────────────────────────────────────────────────
const articleSections = ARTICLES.map((a, i) => {
  const section = buildArticleSection(a, i);
  if (i < ARTICLES.length - 1) {
    section.push(new Paragraph({ children: [new PageBreak()] }));
  }
  return section;
}).flat();

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: NAVY },
        paragraph: {
          spacing: { before: 240, after: 120 },
          outlineLevel: 0,
        },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: MID_BLUE },
        paragraph: {
          spacing: { before: 200, after: 100 },
          outlineLevel: 1,
        },
      },
    ],
  },

  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0,
          format: LevelFormat.BULLET,
          text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },

  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              children: [
                new TextRun({ text: "Article Dataset Report", font: "Arial", size: 18, color: "888888" }),
                new TextRun({ text: "\t", font: "Arial" }),
                new TextRun({ text: "CONFIDENTIAL", font: "Arial", size: 18, bold: true, color: MID_BLUE }),
              ],
              tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
              border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BORDER_C, space: 1 } },
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              children: [
                new TextRun({ text: `Generated by File Export System  ·  ${ARTICLES.length} Articles`, font: "Arial", size: 16, color: "888888" }),
                new TextRun({ text: "\t", font: "Arial" }),
                new TextRun({ text: "Page ", font: "Arial", size: 16, color: "888888" }),
                new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: MID_BLUE }),
                new TextRun({ text: " of ", font: "Arial", size: 16, color: "888888" }),
                new TextRun({ children: [PageNumber.TOTAL_PAGES], font: "Arial", size: 16, color: MID_BLUE }),
              ],
              tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
              border: { top: { style: BorderStyle.SINGLE, size: 4, color: BORDER_C, space: 1 } },
            }),
          ],
        }),
      },

      children: [
        // Cover
        ...buildCoverSection(),

        // TOC
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "TABLE OF CONTENTS", font: "Arial", size: 26, bold: true })] }),
        spacer(80),
        buildTOC(),
        spacer(60),
        new Paragraph({ children: [new PageBreak()] }),

        // Summary stats
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: "DATASET OVERVIEW", font: "Arial", size: 26, bold: true })] }),
        hRule(),
        spacer(80),
        buildSummaryTable(),
        spacer(60),
        new Paragraph({ children: [new PageBreak()] }),

        // All article sections
        ...articleSections,
      ],
    },
  ],
});

const outputPath = process.argv[3];
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log(`DOCX written to ${outputPath}`);
});

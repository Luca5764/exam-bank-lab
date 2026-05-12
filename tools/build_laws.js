const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SOURCE_DIR = path.join(ROOT, '法條');
const OUT_PATH = path.join(ROOT, 'data', 'laws.json');

const LAW_SUMMARIES = {
  '水利法': [
    '水資源屬於國家所有，用水、取水與水利事業興辦都要回到法定管理架構。',
    '考試重點通常集中在主管機關、水權、水利事業、河川與海堤管理、災害防護及罰則。',
    '閱讀順序建議先掌握總則與水權，再看水利建造物、河川管理與行政處分。'
  ],
  '水利法施行細則': [
    '施行細則負責補足水利法的操作定義與行政程序，是理解水利法實務執行的輔助規範。',
    '考試重點通常集中在名詞定義、水權登記、主管機關處理程序與水利事業執行細節。',
    '閱讀時可搭配水利法母法條文，先記定義，再看程序與例外。'
  ],
  '水污染防治法': [
    '核心目標是防治水污染、維持水體用途、管制廢污水排放並建立責任與裁罰制度。',
    '考試重點通常集中在主管機關、事業定義、排放許可、污染防治措施、監測申報與罰則。',
    '閱讀時建議先抓總則與基本措施，再整理許可、管制、裁罰之間的關係。'
  ]
};

const LAW_ORDER = ['水利法.txt', '水利法施行細則.txt', '水污染防治法.txt'];

function normalizeArticleNo(raw) {
  return raw.replace(/\s+/g, '').replace(/[－—]/g, '-');
}

function articleId(no) {
  return `article-${normalizeArticleNo(no).replace(/[^\w\u4e00-\u9fff-]+/g, '-').toLowerCase()}`;
}

function lawId(title, fallback) {
  const known = {
    '水利法': 'water-act',
    '水利法施行細則': 'water-act-enforcement-rules',
    '水污染防治法': 'water-pollution-control-act'
  };
  if (known[title]) return known[title];
  return fallback
    .replace(/\.[^.]+$/, '')
    .replace(/\s+/g, '-')
    .replace(/[^\w-]+/g, '')
    .toLowerCase() || 'law';
}

function chapterId(index) {
  return `chapter-${index + 1}`;
}

function pushArticle(law, currentChapter, currentArticle) {
  if (!currentArticle) return;

  currentArticle.text = currentArticle.text.trim();
  currentArticle.explanation = currentArticle.explanation.trim();

  if (!currentChapter) {
    currentChapter = {
      id: chapterId(law.chapters.length),
      no: '',
      title: '未分章',
      articles: []
    };
    law.chapters.push(currentChapter);
  }

  currentChapter.articles.push(currentArticle);
}

function parseLawFile(fileName) {
  const filePath = path.join(SOURCE_DIR, fileName);
  const source = fs.readFileSync(filePath, 'utf8').replace(/\r\n/g, '\n');
  const lines = source.split('\n');
  const title = lines.find((line) => line.trim())?.trim() || fileName.replace(/\.txt$/i, '');

  const law = {
    id: lawId(title, fileName),
    title,
    sourceFile: `法條/${fileName}`,
    summary: LAW_SUMMARIES[title] || [
      '本整理包含法條與解釋，可依法律與章節篩選閱讀。',
      '建議先掌握總則、主管機關與罰則，再回頭整理細節。'
    ],
    chapters: []
  };

  let currentChapter = null;
  let currentArticle = null;
  let mode = 'text';

  lines.slice(1).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;

    const chapterMatch = line.match(/^第\s*([一二三四五六七八九十百零0-9]+)\s*章\s*(.*)$/);
    if (chapterMatch) {
      pushArticle(law, currentChapter, currentArticle);
      currentArticle = null;
      mode = 'text';
      currentChapter = {
        id: chapterId(law.chapters.length),
        no: chapterMatch[1],
        title: `第 ${chapterMatch[1]} 章${chapterMatch[2] ? ` ${chapterMatch[2].trim()}` : ''}`,
        articles: []
      };
      law.chapters.push(currentChapter);
      return;
    }

    const articleMatch = line.match(/^第\s*([一二三四五六七八九十百零0-9\-－—]+)\s*條/);
    if (articleMatch) {
      pushArticle(law, currentChapter, currentArticle);
      const no = normalizeArticleNo(articleMatch[1]);
      currentArticle = {
        id: articleId(line),
        no,
        title: line,
        text: '',
        explanation: ''
      };
      mode = 'text';
      return;
    }

    const explanationMatch = line.match(/^解釋[：:]\s*(.*)$/);
    if (explanationMatch && currentArticle) {
      mode = 'explanation';
      if (explanationMatch[1]) {
        currentArticle.explanation += `${explanationMatch[1].trim()}\n`;
      }
      return;
    }

    if (!currentArticle) return;
    if (mode === 'explanation') currentArticle.explanation += `${line}\n`;
    else currentArticle.text += `${line}\n`;
  });

  pushArticle(law, currentChapter, currentArticle);
  return law;
}

function countArticles(law) {
  return law.chapters.reduce((sum, chapter) => sum + chapter.articles.length, 0);
}

function main() {
  const files = fs.readdirSync(SOURCE_DIR)
    .filter((file) => file.endsWith('.txt'))
    .sort((a, b) => {
      const ai = LAW_ORDER.indexOf(a);
      const bi = LAW_ORDER.indexOf(b);
      if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      return a.localeCompare(b, 'zh-Hant');
    });

  const laws = files.map(parseLawFile).map((law) => ({
    ...law,
    chapterCount: law.chapters.length,
    articleCount: countArticles(law)
  }));

  fs.writeFileSync(OUT_PATH, `${JSON.stringify(laws, null, 2)}\n`, 'utf8');

  laws.forEach((law) => {
    console.log(`${law.title}: ${law.chapterCount} 章 / ${law.articleCount} 條`);
  });
  console.log(`Wrote ${path.relative(ROOT, OUT_PATH)}`);
}

main();

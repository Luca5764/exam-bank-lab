/*
 * Service Worker:讓網站可以加到主畫面、離線刷題。
 * 策略:
 *   - HTML(導覽請求):network-first,離線時退回快取 → 上線時永遠拿最新頁面。
 *   - 靜態資源與 JSON:stale-while-revalidate → 先回快取秒開,背景更新下次生效。
 *   - 題庫:activate 與每次開頁(SYNC_BANKS 訊息)時,依 data/banks.json
 *     把還沒快取的題庫 JSON 補抓進來,做到「沒開過的題庫離線也能刷」。
 * CACHE_VERSION 只在 SW 本身邏輯改動、需要整批重建快取時才要 bump;
 * 內容更新(題庫、css、js)靠上面的策略自動換新,不必動版本號。
 */
const CACHE_VERSION = 'v1';
const CACHE_NAME = `quiz-${CACHE_VERSION}`;

// 頁面殼:安裝時就快取,保證離線開得起來
const CORE_ASSETS = [
  'index.html',
  'quiz.html',
  'browse.html',
  'wrong.html',
  'review.html',
  'laws.html',
  'changelog.html',
  'css/style.css',
  'js/shared.js',
  'assets/vendor/embla/embla-carousel.umd.js',
  'manifest.json',
  'assets/icons/icon-192.png',
  'assets/icons/icon-512.png',
];

// 資料檔:跟題庫一起在背景補抓(缺哪個抓哪個,失敗不影響其他)
const DATA_ASSETS = [
  'data/banks.json',
  'data/changelog.json',
  'data/laws.json',
  'data/law-links.json',
  'data/law-explanation-layouts.json',
  'data/overrides.json',
  'data/safety_law_amendments.json',
  'data/traffic_law_amendments.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    // 個別 add,單一檔案失敗不要讓整個安裝失敗
    await Promise.allSettled(CORE_ASSETS.map((url) => cache.add(url)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)));
    await self.clients.claim();
    await syncBanks();
  })());
});

// 補抓還沒快取的資料檔與題庫 JSON(已存在的不重抓,流量很小)
async function syncBanks() {
  const cache = await caches.open(CACHE_NAME);

  let bankFiles = [];
  try {
    const res = await fetch('data/banks.json', { cache: 'no-cache' });
    if (res.ok) {
      const banks = await res.clone().json();
      await cache.put('data/banks.json', res);
      bankFiles = banks.map((b) => b && b.file).filter(Boolean);
    }
  } catch {
    return; // 離線就下次再說
  }

  const targets = [...DATA_ASSETS.filter((u) => u !== 'data/banks.json'), ...bankFiles];
  await Promise.allSettled(targets.map(async (url) => {
    const encoded = encodeURI(url); // 題庫檔名含中文
    const hit = await cache.match(encoded, { ignoreSearch: true });
    if (hit) return;
    const res = await fetch(encoded);
    if (res.ok) await cache.put(encoded, res);
  }));
}

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SYNC_BANKS') {
    event.waitUntil(syncBanks());
  }
});

const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // 字型:cache-first(內容不會變,離線也要有字)
  if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  if (url.origin !== self.location.origin) return;

  // 頁面:network-first,確保上線時拿到最新 HTML
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }

  // 其餘同源資源(css/js/json/圖片):stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) cache.put(request, res.clone());
  return res;
}

// 訊號很弱的「lie-fi」(連得上但一直不回應)下,fetch 不會立刻失敗,
// 頁面會卡到瀏覽器逾時。設一個短逾時:超過就改用快取,有副本就秒開。
const NAV_TIMEOUT_MS = 4000;

async function networkFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request, { ignoreSearch: true });
  try {
    const res = await fetchWithTimeout(request, NAV_TIMEOUT_MS);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch {
    if (cached) return cached;
    // 退無可退時至少回首頁(理論上 CORE_ASSETS 已涵蓋所有頁面)
    const home = await cache.match('index.html');
    if (home) return home;
    throw new Error('offline and not cached');
  }
}

function fetchWithTimeout(request, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return fetch(request, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const hit = await cache.match(request, { ignoreSearch: true });
  const refresh = fetch(request).then((res) => {
    if (res.ok) cache.put(request, res.clone());
    return res;
  }).catch(() => null);
  if (hit) return hit;
  const res = await refresh;
  if (res) return res;
  throw new Error('offline and not cached');
}

// 声優名 → URLスラグ マッピング
export const CV_SLUG_MAP: Record<string, string> = {
  '陽向葵ゅか': 'hyuga-ayuka',
  '神田朱未': 'kanda-akemi',
  '和泉杏': 'izumi-an',
  '月宮めあ': 'tsukimiya-mea',
};

// スラグ → 声優名 の逆引き
export const SLUG_CV_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(CV_SLUG_MAP).map(([name, slug]) => [slug, name])
);

export function cvToSlug(name: string): string {
  return CV_SLUG_MAP[name] ?? name.toLowerCase().replace(/\s+/g, '-');
}

export function slugToCv(slug: string): string | undefined {
  return SLUG_CV_MAP[slug];
}

/**
 * FANZAアフィリエイトリンク生成ユーティリティ
 * 環境変数 FANZA_AF_ID が設定されていれば使用。未設定の場合は yukine0423-002 固定。
 */
export function fanzaAffiliateUrl(cid: string): string {
  const afId = import.meta.env.FANZA_AF_ID || 'yukine0423-002';
  const target = `https://www.dmm.co.jp/dc/doujin/-/detail/=/cid=${cid}/`;
  const encoded = encodeURIComponent(target);
  return `https://al.fanza.co.jp/?lurl=${encoded}&af_id=${afId}&ch=toolbar_sp&ch_id=link`;
}

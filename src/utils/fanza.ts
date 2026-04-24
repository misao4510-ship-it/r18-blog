/**
 * FANZAアフィリエイトリンク生成ユーティリティ
 * 環境変数 FANZA_AF_ID が設定されていれば af 付きリンクを返す。
 * 未設定の場合は DMM 直リンクにフォールバック。
 */
export function fanzaAffiliateUrl(cid: string): string {
  const afId = import.meta.env.FANZA_AF_ID;
  const target = `https://www.dmm.co.jp/dc/doujin/-/detail/=/cid=${cid}/`;
  if (!afId) return target;
  const encoded = encodeURIComponent(target);
  return `https://al.fanza.co.jp/?lurl=${encoded}&af_id=${afId}&ch=toolbar_sp&ch_id=link`;
}

/**
 * 고정 주소 → 오라클 서버 중계.
 *
 * 왜 필요한가: 무료 임시 터널(trycloudflare.com)은 서버가 터널을 다시 열 때마다
 * 주소가 바뀐다. 발표나 팀 공유에는 안 바뀌는 주소가 있어야 해서, 이 워커가
 * 고정 주소를 맡고 뒤쪽 주소만 갈아끼운다.
 *
 * 답변은 한 글자씩 흘러나오므로 응답 본문을 모으지 않고 그대로 흘려보낸다.
 */
export default {
  async fetch(request, env) {
    const src = new URL(request.url);
    const target = new URL(env.ORIGIN);
    target.pathname = src.pathname;
    target.search = src.search;

    const headers = new Headers(request.headers);
    headers.set("Host", target.host);

    const resp = await fetch(target.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD"
        ? undefined : request.body,
      redirect: "manual",
    });

    // 스트리밍을 끊지 않도록 본문(resp.body)을 그대로 넘긴다.
    const out = new Response(resp.body, resp);
    out.headers.set("Cache-Control", "no-store");
    return out;
  },
};

from dataclasses import dataclass, field

import httpx

from .config import settings

# Puppeteer function run by browserless v2's /function: an ES module whose return value comes back as
# JSON as-is (v1's `module.exports` is rejected and a {data, type} envelope is not unwrapped).
# Captures rendered HTML, cookies, and network request/response metadata.
_RENDER_SCRIPT = """\
export default async function ({ page, context }) {
  const requests = [];
  page.on('response', async (response) => {
    try {
      requests.push({
        url: response.url(),
        method: response.request().method(),
        status: response.status(),
        response_headers: response.headers()
      });
    } catch (_) {}
  });

  await page.goto(context.url, { waitUntil: 'networkidle0', timeout: 30000 });

  const html = await page.content();
  const cookies = await page.cookies();

  return { html, cookies, requests };
}
"""


@dataclass
class BrowserlessResult:
    html: str
    cookies: list = field(default_factory=list)
    response_metadata: dict = field(default_factory=dict)


class BrowserlessClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(timeout=60.0)

    def render(self, url: str) -> BrowserlessResult:
        params = {"token": self._token} if self._token else {}
        response = self._http.post(
            f"{self._base_url}/function",
            json={"code": _RENDER_SCRIPT, "context": {"url": url}},
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return BrowserlessResult(
            html=data["html"],
            cookies=data.get("cookies", []),
            response_metadata={"requests": data.get("requests", [])},
        )

    def close(self) -> None:
        self._http.close()


_instance: BrowserlessClient | None = None


def get_browserless() -> BrowserlessClient:
    global _instance
    if _instance is None:
        _instance = BrowserlessClient(
            base_url=settings.browserless_url,
            token=settings.browserless_token,
        )
    return _instance

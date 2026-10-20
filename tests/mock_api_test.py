"""端到端测试：用本地 mock 服务验证"截图 → 切带 → 请求 → 解析 → 缓存"整条链路。

不需要真实 API Key。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cache import AnswerCache  # noqa: E402
from app.config import Config  # noqa: E402
from app import solver  # noqa: E402

CAPTURED: list[dict] = []

CANNED = {
    "answers": [
        {"no": 1, "type": "单选题", "stem": "维护重点经济领域安全面临的风险挑战不包括",
         "answer": ["B"], "option_text": "经济主权安全风险", "confidence": 0.95,
         "reason": "重点经济领域指金融、粮食、能源资源与产业链供应链安全。"},
        {"no": 2, "type": "单选题", "stem": "推进中国式现代化的生力军",
         "answer": ["B"], "option_text": "民营经济", "confidence": 0.93,
         "reason": "民营经济是生力军。"},
        {"no": 3, "type": "判断题", "stem": "经济安全是国家安全的基础",
         "answer": ["对"], "option_text": "对", "confidence": 0.9, "reason": "教材原文。"},
    ]
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        CAPTURED.append(body)

        payload = {
            "id": "mock", "object": "chat.completion", "created": 0,
            "model": body.get("model", "mock"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant",
                            "content": json.dumps(CANNED, ensure_ascii=False)},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def make_quiz_image(height: int = 900) -> np.ndarray:
    """造一张"白底 + 若干黑条"的假截图（BGR）。"""
    img = np.full((height, 1400, 3), 245, dtype=np.uint8)
    y = 40
    while y < height - 40:
        img[y : y + 26, 60 : 60 + 900] = 30
        y += 70
    return img


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    cfg = Config()
    cfg.set("api.base_url", f"http://127.0.0.1:{port}/v1")
    cfg.set("api.api_key", "sk-mock")
    cfg.set("api.model", "deepseek-flash")
    cfg.set("behavior.vote_low_confidence", False)
    cfg.set("behavior.use_cache", True)

    cache = AnswerCache(Path(__file__).resolve().parent / "test_cache.db")
    cache.clear()

    statuses: list[str] = []
    answers = solver.solve(make_quiz_image(900), cfg, cache, statuses.append)

    print("状态流:", " -> ".join(statuses))
    print(f"解析出 {len(answers)} 题")
    for a in answers:
        print(f"  第{a.no}题 {a.qtype} -> {a.badge}  {a.option_text}  ({a.confidence:.0%})")

    assert len(answers) == 3, answers
    assert answers[0].letters == ["B"]
    assert answers[2].letters == ["对"]

    # 请求体检查
    body = CAPTURED[0]
    assert body["model"] == "deepseek-flash", body["model"]
    user_content = body["messages"][1]["content"]
    blocks = [b for b in user_content if b.get("type") == "image_url"]
    print(f"图片块数量: {len(blocks)}（900px 高应为 1 张）")
    assert len(blocks) == 1, len(blocks)
    url = blocks[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,"), url[:40]
    assert blocks[0]["image_url"]["detail"] == "high"

    # 长图应该被切成多张
    CAPTURED.clear()
    long_img = make_quiz_image(2600)
    solver.solve(long_img, cfg, cache, None)
    n = len([b for b in CAPTURED[0]["messages"][1]["content"] if b.get("type") == "image_url"])
    print(f"2600px 高切成了 {n} 张图")
    assert n >= 2, n

    # 缓存命中：同一张图第二次不应再发请求
    CAPTURED.clear()
    solver.solve(long_img, cfg, cache, None)
    assert len(CAPTURED) == 0, "缓存未命中"
    print("缓存命中校验通过")

    cache.close()
    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

# 防止 cp1252 stdout 把中文输出变成 UnicodeEncodeError（CI 上会直接挂）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    protocol_version = "HTTP/1.1"

    def _chunked_events(self, content: str) -> bytes:
        """把完整回复切成 SSE 事件流，模拟流式端点。"""
        events = []
        step = max(1, len(content) // 12)
        pieces = [content[k:k + step] for k in range(0, len(content), step)] or [""]
        for piece in pieces:
            events.append({
                "id": "mock", "object": "chat.completion.chunk", "created": 0,
                "model": "mock",
                "choices": [{"index": 0, "delta": {"content": piece},
                             "finish_reason": None}],
            })
        events.append({
            "id": "mock", "object": "chat.completion.chunk", "created": 0,
            "model": "mock",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        return "".join(
            "data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events
        ).encode("utf-8") + b"data: [DONE]\n\n"

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        CAPTURED.append(body)

        content = json.dumps(CANNED, ensure_ascii=False)
        if body.get("stream"):
            data = self._chunked_events(content)
            ctype = "text/event-stream"
        else:
            payload = {
                "id": "mock", "object": "chat.completion", "created": 0,
                "model": body.get("model", "mock"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ctype = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
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
    partials: list[list] = []
    answers = solver.solve(make_quiz_image(900), cfg, cache, statuses.append,
                           partial=partials.append)

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

    # 流式默认开启：请求带 stream，且答案逐题到达（1 题 -> 2 题 -> 3 题）
    assert body.get("stream") is True, "stream 应默认开启"
    steps = [len(p) for p in partials]
    print(f"流式逐题回调: {steps}")
    assert steps == [1, 2, 3], steps
    assert [a.letters for a in partials[-1]] == [a.letters for a in answers]

    # 思考等级：默认 low，并且 extra_body 的 thinking 要真的落到请求体顶层
    assert body.get("reasoning_effort") == "low", body.get("reasoning_effort")
    assert body.get("thinking") == {"type": "enabled"}, body.get("thinking")
    print(f"思考参数: reasoning_effort={body.get('reasoning_effort')} thinking={body.get('thinking')}")

    # off 档要变成 disabled 且不下发 reasoning_effort
    cfg.set("api.thinking", "off")
    CAPTURED.clear()
    solver.solve(make_quiz_image(905), cfg, cache, None)
    off_body = CAPTURED[0]
    assert "reasoning_effort" not in off_body, off_body.get("reasoning_effort")
    assert off_body.get("thinking") == {"type": "disabled"}, off_body.get("thinking")
    print(f"关闭思考: reasoning_effort 未下发, thinking={off_body.get('thinking')}")
    cfg.set("api.thinking", "low")
    CAPTURED.clear()

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

    # 关闭流式：请求不带 stream 参数，也不再逐题回调
    cfg.set("api.stream", False)
    CAPTURED.clear()
    partials.clear()
    solver.solve(make_quiz_image(932), cfg, cache, None, partial=partials.append)
    assert "stream" not in CAPTURED[0], CAPTURED[0].get("stream")
    assert not partials, "非流式不应有逐题回调"
    print("关闭流式校验通过")

    cache.close()
    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""求解器：截图直接交给视觉模型，返回结构化答案。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import imageutil
from .cache import AnswerCache

StatusFn = Callable[[str], None]


@dataclass
class Answer:
    no: int
    qtype: str
    stem: str
    letters: list[str] = field(default_factory=list)
    option_text: str = ""
    confidence: float = 0.0
    reason: str = ""
    option_texts: list[str] = field(default_factory=list)
    from_cache: bool = False

    @property
    def badge(self) -> str:
        return "".join(self.letters) or "?"

    @property
    def is_multi(self) -> bool:
        return len(self.letters) > 1 and all(
            len(l) == 1 and l.upper() in "ABCDEFGH" for l in self.letters
        )

    def _texts(self) -> list[str]:
        if self.option_texts:
            return [t for t in self.option_texts if t]
        if self.option_text:
            return _split_option_text(self.option_text, len(self.letters))
        return []

    def display_rows(self) -> list[str]:
        """卡片正文。多选一行一个选项，单选/判断只显示原文。"""
        texts = self._texts()
        if self.is_multi and len(texts) == len(self.letters):
            return [f"{L}. {t}" for L, t in zip(self.letters, texts)]
        if texts:
            return ["；".join(texts)] if len(texts) > 1 else [texts[0]]
        if self.letters:
            return [" / ".join(self.letters)]
        return ["（未解析）"]


_SPLIT_RE = re.compile(r"\s*[；;｜|]\s*")


def _split_option_text(text: str, expect: int) -> list[str]:
    """老格式只有一整个字符串时，按分号拆开凑多选。"""
    if expect <= 1:
        return [text.strip()] if text.strip() else []
    parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
    return parts


SYSTEM_PROMPT = """你是中国高校课程答题助手。用户发来的是网页上的题目截图。
请识别截图中的全部题目并作答。严格只输出一个 JSON 对象，不要 Markdown 代码块、不要任何解释文字。

格式：
{"answers":[{"no":1,"type":"多选题","stem":"题干(可截断到40字)","answer":["A","C"],"option_texts":["所选第一个选项的完整原文","所选第二个选项的完整原文"],"confidence":0.9,"reason":"不超过60字"}]}

规则：
1. no 用页面上显示的题号；页面没写题号就按出现顺序从 1 编号。
2. type 取 单选题/多选题/判断题/填空题/简答题/名词解释/论述题。
3. answer：选择题填选项字母（大写，多选按字母升序，如 ["A","C"]）；判断题填 ["对"] 或 ["错"]；填空/简答把答案原文填进去。
4. option_texts 是与 answer 一一对应、顺序一致的选项原文数组：单选/判断题给单元素数组，多选给每个选中选项各一条，填空题填答案原文。这份原文用户要照着去页面上点，务必逐字抄准。
5. confidence 是你对该题答案真实把握的 0~1 小数。
6. 只依据图片内容作答，看不清就降低 confidence，绝对不要编造题目。
7. 一次给了多张图片时，它们是同一页面的上下连续片段且彼此有重叠：按顺序拼读，同一道题只答一次。
8. 页面上若出现"我的答案""正确答案"等回显，不要把它当成你的答案，请独立作答。"""


# --------------------------------------------------------------------------
# JSON 抽取（模型偶尔会带 ```json 围栏或前后废话）
# --------------------------------------------------------------------------
def extract_json(text: str) -> dict | None:
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    start, depth = None, 0
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(s[start : i + 1])
                except Exception:
                    start = None
    return None


_LETTER_RE = re.compile(r"[A-H]")
_YES = {"对", "正确", "√", "T", "TRUE", "是"}
_NO = {"错", "错误", "×", "F", "FALSE", "否"}


def _norm_answer(raw: Any, qtype: str) -> list[str]:
    parts = [str(x) for x in raw] if isinstance(raw, (list, tuple)) else [str(raw)]
    joined = "".join(parts).strip()
    if qtype in ("判断题",) or joined in _YES or joined in _NO:
        if joined in _YES or joined.upper() in _YES:
            return ["对"]
        if joined in _NO or joined.upper() in _NO:
            return ["错"]
        if qtype == "判断题":
            return [joined or "?"]
        return [joined] if joined else []
    letters = sorted(set(_LETTER_RE.findall(joined.upper())))
    return letters or ([joined] if joined else [])


def _build_answers(payload: dict) -> list[Answer]:
    items = payload.get("answers")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []

    out: list[Answer] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        try:
            no = int(it.get("no", i + 1))
        except Exception:
            no = i + 1
        qtype = str(it.get("type") or "单选题").strip()
        try:
            conf = float(it.get("confidence", 0.0))
        except Exception:
            conf = 0.0
        letters = _norm_answer(it.get("answer", []), qtype) or ["?"]

        # option_texts 是标准字段；option_text 是旧格式/兜底
        texts: list[str] = []
        raw_texts = it.get("option_texts")
        if isinstance(raw_texts, (list, tuple)):
            texts = [str(t).strip() for t in raw_texts if str(t).strip()]
        elif isinstance(raw_texts, str) and raw_texts.strip():
            texts = _split_option_text(raw_texts, len(letters))

        out.append(
            Answer(
                no=no,
                qtype=qtype,
                stem=str(it.get("stem") or "").strip(),
                letters=letters,
                option_text=str(it.get("option_text") or "").strip(),
                confidence=max(0.0, min(1.0, conf)),
                reason=str(it.get("reason") or "").strip(),
                option_texts=texts,
            )
        )
    return sorted(out, key=lambda a: a.no)


# --------------------------------------------------------------------------
# 调用
# --------------------------------------------------------------------------
def _client(cfg):
    from openai import OpenAI

    return OpenAI(
        api_key=cfg.get("api.api_key") or "sk-none",
        base_url=cfg.get("api.base_url"),
        timeout=float(cfg.get("api.timeout", 90)),
        max_retries=1,
    )


THINKING_LEVELS = ("off", "low", "high", "max")


def thinking_kwargs(cfg) -> dict[str, Any]:
    """把 api.thinking 翻译成请求参数。

    DeepSeek 的 deepseek-flash 默认就是「思考开启 + effort=high」，
    不显式传的话等于一直在用最高档，又慢又贵。
    思考模式下 temperature / presence_penalty / frequency_penalty 会被忽略。
    """
    level = str(cfg.get("api.thinking", "low") or "low").strip().lower()
    if level not in THINKING_LEVELS:
        level = "low"
    if level == "off":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {
        "reasoning_effort": level,
        "extra_body": {"thinking": {"type": "enabled"}},
    }


# 兼容端点不认这些参数时会报错，报错信息里通常带其中之一
_EXTRA_KEYS = ("reasoning_effort", "extra_body", "thinking")


def _chat(cfg, messages, want_json: bool = True) -> str:
    client = _client(cfg)
    kwargs: dict[str, Any] = {
        "model": cfg.get("api.model"),
        "messages": messages,
        "temperature": float(cfg.get("api.temperature", 0)),
        "max_tokens": int(cfg.get("api.max_tokens", 2000)),
    }
    kwargs.update(thinking_kwargs(cfg))
    if want_json:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e:
        # 某些 OpenAI 兼容端点不认 json_object，也可能不认思考参数，各降级一次
        err = str(e).lower()
        dropped = False
        if want_json and "response_format" in err:
            kwargs.pop("response_format", None)
            dropped = True
        if any(k in err for k in _EXTRA_KEYS):
            for k in _EXTRA_KEYS:
                kwargs.pop(k, None)
            dropped = True
        if not dropped:
            raise
        resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def _refine_low_confidence(cfg, messages, answers: list[Answer]) -> list[Answer]:
    """低置信度的题再问一次（独立采样），取更有把握的那版。"""
    threshold = float(cfg.get("behavior.low_confidence", 0.70))
    if not any(a.confidence < threshold for a in answers):
        return answers
    retry_messages = messages + [
        {"role": "assistant", "content": json.dumps(
            {"answers": [{"no": a.no, "answer": a.letters} for a in answers]},
            ensure_ascii=False)},
        {"role": "user", "content": (
            f"上面这些答案里有把握不足的（confidence < {threshold}）。"
            "请重新审视每一道题，给出你认为最正确的答案，同样只输出 JSON。"
        )},
    ]
    try:
        again = _build_answers(extract_json(_chat(cfg, retry_messages)) or {})
    except Exception:
        return answers
    best = {a.no: a for a in again}
    return [max((a, best[a.no]), key=lambda x: x.confidence) if a.no in best else a for a in answers]


def image_key(strips: list[bytes]) -> str:
    h = hashlib.sha256()
    for b in strips:
        h.update(b)
    return h.hexdigest()


def solve(
    bgr: np.ndarray,
    cfg,
    cache: AnswerCache | None = None,
    status: StatusFn | None = None,
    hint: str = "",
) -> list[Answer]:
    """核心入口：BGR 截图 → 答案列表。"""
    if status:
        status("切图中…")
    strips = imageutil.strip_images(bgr, target_h=int(cfg.get("capture.strip_h", 1000)))
    key = image_key(strips)

    if cache is not None and cfg.get("behavior.use_cache", True):
        hit = cache.get(key)
        if hit:
            answers = _build_answers(hit)
            for a in answers:
                a.from_cache = True
            if status:
                status(f"缓存命中 · {len(answers)} 题")
            return answers

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"下面是同一页面截图切成的 {len(strips)} 张上下连续图片，请识别并作答。"
                + (f"\n补充信息：{hint}" if hint else "")
            ),
        }
    ]
    for b in strips:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(b).decode("ascii"),
                    "detail": "high",
                },
            }
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    if status:
        status("AI 识别中…")
    payload = extract_json(_chat(cfg, messages))
    if payload is None:
        raise RuntimeError("模型没有返回可解析的 JSON，检查模型名是否为支持图片输入的 deepseek-flash")
    answers = _build_answers(payload)
    if not answers:
        raise RuntimeError("模型没有识别到题目，试试重新框选（F7）")

    if cfg.get("behavior.vote_low_confidence", True):
        if status:
            status("复核低置信度题目…")
        answers = _refine_low_confidence(cfg, messages, answers)

    if cache is not None:
        cache.put(key, payload)
    return answers


def test_connection(cfg) -> str:
    text = _chat(
        cfg,
        [
            {"role": "system", "content": "只回复两个字：正常"},
            {"role": "user", "content": "连通性测试"},
        ],
        want_json=False,
    )
    return text[:80]
